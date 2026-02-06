from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance

app = FastAPI(title="Amazon Image Auto Editor")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "ok"}

# ---------------- REMOVE BG ----------------
def remove_bg(image_bytes: bytes) -> bytes:
    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
    )
    return r.content

# ---------------- BACKGROUND COLOR ----------------
def resolve_background(bg_color: str):
    presets = {
        "white": (255, 255, 255),
        "offwhite": (245, 245, 245),
        "lightgrey": (240, 240, 240),
        "black": (0, 0, 0),
    }
    if bg_color.startswith("#"):
        return tuple(int(bg_color[i:i+2], 16) for i in (1,3,5))
    return presets.get(bg_color, (255,255,255))

# ---------------- SMART CROP ----------------
def smart_crop_rgba(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

# ---------------- ENHANCEMENT ----------------
def enhance_image(img: Image.Image) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(1.05)
    return img

# ---------------- SHADOW ----------------
def apply_shadow(img):
    shadow = img.copy().convert("RGBA")
    shadow = shadow.point(lambda p: p * 0.3)
    return shadow

def generate_amazon_set(transparent_bytes: bytes):
    outputs = {}

    # 1️⃣ MAIN IMAGE
    main = amazon_ready_image(transparent_bytes)
    outputs["01_main.jpg"] = main

    # 2️⃣ ZOOM IMAGE (closer crop)
    img = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    zoom = img.resize((1800,1800), Image.LANCZOS)
    canvas = Image.new("RGB",(2000,2000),(255,255,255))
    canvas.paste(zoom,(100,100),zoom)

    buf = io.BytesIO()
    canvas.save(buf,"JPEG",quality=95)
    outputs["02_zoom.jpg"] = buf.getvalue()

    # 3️⃣ CLEAN PRODUCT (no margin)
    buf2 = io.BytesIO()
    img.convert("RGB").save(buf2,"JPEG",quality=95)
    outputs["03_cut.jpg"] = buf2.getvalue()

    return outputs

# ---------------- AMAZON READY ----------------
def amazon_ready_image(img_bytes: bytes, bg_color="white", add_shadow=0):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    CANVAS = 2000
    FILL_RATIO = 0.85
    target = int(CANVAS * FILL_RATIO)

    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA", (CANVAS, CANVAS), (*bg_rgb, 255))

    x = (CANVAS - img.width) // 2
    y = (CANVAS - img.height) // 2
    background.paste(img, (x, y), img)

    if add_shadow == 1:
        background = apply_shadow(background)

    background = enhance_image(background)

    out = io.BytesIO()
    background.convert("RGB").save(out, "JPEG", quality=95)
    return out.getvalue()

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent, bg_color, add_shadow)

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

# ---------------- VALIDATOR ----------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    w, h = img.size
    return {"square": w == h, "resolution_ok": w >= 1600}

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for f in files:
            img_bytes = await f.read()
            transparent = remove_bg(img_bytes)
            final = amazon_ready_image(transparent)
            zipf.writestr(f"amazon_{f.filename}", final)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=amazon_images.zip"}
    )

@app.post("/process/amazon-set")
async def amazon_set(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    images = generate_amazon_set(transparent)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for name,data in images.items():
            zipf.writestr(name,data)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_listing_images.zip"}
    )
