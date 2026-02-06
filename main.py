from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter
from datetime import datetime

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

# ---------- DAILY LIMIT SETTINGS ----------
DAILY_LIMIT = 10
usage_store = {}

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "ok"}

# ---------------- DAILY LIMIT FUNCTION ----------------
def check_daily_limit(ip: str):

    today = datetime.utcnow().date()

    if ip not in usage_store:
        usage_store[ip] = {"date": today, "count": 0}

    if usage_store[ip]["date"] != today:
        usage_store[ip] = {"date": today, "count": 0}

    if usage_store[ip]["count"] >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Daily free limit reached")

    usage_store[ip]["count"] += 1

# ---------------- REMOVE BG ----------------
def remove_bg(image_bytes: bytes) -> bytes:
    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
    )
    return r.content

# ---------------- IMAGE HELPERS ----------------
def smart_crop_rgba(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

def studio_lighting_correction(img):
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = img.filter(ImageFilter.SMOOTH)
    return img

def amazon_ready_image(img_bytes: bytes):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    CANVAS = 2000
    target = int(CANVAS * 0.90)

    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    background = Image.new("RGBA", (CANVAS, CANVAS), (255,255,255,255))
    x = (CANVAS - img.width)//2
    y = (CANVAS - img.height)//2
    background.paste(img,(x,y),img)

    background = studio_lighting_correction(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95)
    return out.getvalue()

def luxury_studio_lighting(img_rgba):

    CANVAS = 2000

    # white luxury gradient background
    bg = Image.new("RGB",(CANVAS,CANVAS),(255,255,255))
    glow = Image.new("RGB",(CANVAS,CANVAS),(245,245,245))
    mask = Image.radial_gradient("L").resize((CANVAS,CANVAS))
    bg = Image.composite(glow,bg,mask)

    # resize product
    w,h = img_rgba.size
    target = int(CANVAS*0.85)
    scale = min(target/w, target/h)
    img_rgba = img_rgba.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    x = (CANVAS-img_rgba.width)//2
    y = (CANVAS-img_rgba.height)//2

    bg.paste(img_rgba,(x,y),img_rgba)

    # lighting polish
    bg = ImageEnhance.Brightness(bg).enhance(1.05)
    bg = ImageEnhance.Contrast(bg).enhance(1.08)
    bg = ImageEnhance.Sharpness(bg).enhance(1.15)

    return bg

def luxury_lifestyle_scene(img_rgba):

    CANVAS = 2000

    # soft marble luxury background
    bg = Image.new("RGB",(CANVAS,CANVAS),(250,250,250))

    # slight gradient
    grad = Image.new("RGB",(CANVAS,CANVAS),(235,235,235))
    mask = Image.linear_gradient("L").resize((CANVAS,CANVAS))
    bg = Image.composite(grad,bg,mask)

    # resize product
    w,h = img_rgba.size
    target = int(CANVAS*0.65)
    scale = min(target/w, target/h)
    img_rgba = img_rgba.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    x = (CANVAS-img_rgba.width)//2
    y = int(CANVAS*0.25)

    bg.paste(img_rgba,(x,y),img_rgba)

    # premium lighting
    bg = ImageEnhance.Brightness(bg).enhance(1.05)
    bg = ImageEnhance.Contrast(bg).enhance(1.08)

    return bg

def apply_logo_watermark(product_bytes: bytes, logo_bytes: bytes):

    base = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")

    # resize logo proportional
    bw, bh = base.size
    lw, lh = logo.size

    target_w = int(bw * 0.18)
    scale = target_w / lw
    logo = logo.resize((int(lw*scale), int(lh*scale)), Image.LANCZOS)

    # position bottom-right
    x = bw - logo.width - 40
    y = bh - logo.height - 40

    base.paste(logo, (x, y), logo)

    out = io.BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=95)
    return out.getvalue()

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(request: Request, file: UploadFile = File(...)):

    ip = request.client.host
    check_daily_limit(ip)

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)

    return StreamingResponse(
        io.BytesIO(final),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=amazon_{file.filename}"}
    )

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            transparent = remove_bg(img_bytes)
            final = amazon_ready_image(transparent)
            zipf.writestr(f"amazon_{f.filename}", final)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )

@app.post("/process/studio")
async def studio(file: UploadFile = File(...)):

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    img = Image.open(io.BytesIO(transparent)).convert("RGBA")
    final = luxury_studio_lighting(img)

    out = io.BytesIO()
    final.save(out,"JPEG",quality=95)

    return StreamingResponse(
        io.BytesIO(out.getvalue()),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=studio_{file.filename}"}
    )

@app.post("/process/lifestyle")
async def lifestyle(file: UploadFile = File(...)):

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    img = Image.open(io.BytesIO(transparent)).convert("RGBA")
    final = luxury_lifestyle_scene(img)

    out = io.BytesIO()
    final.save(out,"JPEG",quality=95)

    return StreamingResponse(
        io.BytesIO(out.getvalue()),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=lifestyle_{file.filename}"}
    )

@app.post("/process/add-logo")
async def add_logo(
    image: UploadFile = File(...),
    logo: UploadFile = File(...)
):

    image_bytes = await image.read()
    logo_bytes = await logo.read()

    result = apply_logo_watermark(image_bytes, logo_bytes)

    return StreamingResponse(
        io.BytesIO(result),
        media_type="image/jpeg",
        headers={"Content-Disposition": "attachment; filename=branded.jpg"}
    )
