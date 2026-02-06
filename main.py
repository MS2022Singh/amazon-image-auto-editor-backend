from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter
from datetime import date

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")
OWNER_KEY = os.getenv("OWNER_KEY","owner123")
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT","25"))

usage_db = {}

@app.get("/")
def root():
    return {"status": "ok"}

# ---------------- USAGE LIMITER ----------------
async def check_usage(request: Request):
    api_key = request.headers.get("X-API-KEY","public")

    if api_key == OWNER_KEY:
        return

    today = str(date.today())

    if api_key not in usage_db:
        usage_db[api_key] = {"date": today, "count": 0}

    if usage_db[api_key]["date"] != today:
        usage_db[api_key] = {"date": today, "count": 0}

    if usage_db[api_key]["count"] >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Daily limit reached")

    usage_db[api_key]["count"] += 1

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

def amazon_smart_framing(img, canvas=2000):
    img = smart_crop_rgba(img)

    fill = 0.92
    target = int(canvas * fill)

    w,h = img.size
    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg = Image.new("RGBA",(canvas,canvas),(255,255,255,255))
    x = (canvas-img.width)//2
    y = (canvas-img.height)//2
    bg.paste(img,(x,y),img)

    return bg

def enhance_pipeline(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = img.filter(ImageFilter.SMOOTH)
    return img

# ---------------- AMAZON READY ----------------
def amazon_ready_image(img_bytes: bytes, add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    background = amazon_smart_framing(img)

    if add_shadow == 1:
        shadow = background.point(lambda p: p * 0.3)
        background.paste(shadow,(0,0),shadow)

    background = enhance_pipeline(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95)
    return out.getvalue()

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(
    request: Request,
    file: UploadFile = File(...),
    add_shadow: int = Form(0)
):
    await check_usage(request)

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent, add_shadow)

    return StreamingResponse(
        io.BytesIO(final),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=amazon_{file.filename}"}
    )

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(request: Request, file: UploadFile = File(...)):
    await check_usage(request)

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(request: Request, files: list[UploadFile] = File(...)):
    await check_usage(request)

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
