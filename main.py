from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

@app.get("/")
def root():
    return {"status":"ok"}

# ---------------- REMOVE BG SAFE ----------------
def remove_bg_safe(image_bytes: bytes) -> bytes:
    if not REMOVEBG_API_KEY:
        return image_bytes
    try:
        r = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            headers={"X-Api-Key": REMOVEBG_API_KEY},
            files={"image_file": image_bytes},
            data={"size": "auto"},
            timeout=20
        )
        if r.status_code == 200:
            return r.content
        return image_bytes
    except Exception:
        return image_bytes

# ---------------- IMAGE HELPERS ----------------
def smart_crop_rgba(img):
    if img.mode != "RGBA":
        return img
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

def remove_reflection(img):
    return img.filter(ImageFilter.SMOOTH_MORE)

def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.12)
    return img

def resolve_background(bg_color):
    presets = {
        "white": (255,255,255),
        "offwhite": (245,245,245),
        "lightgrey": (240,240,240),
        "black": (0,0,0)
    }
    if bg_color.startswith("#"):
        return tuple(int(bg_color[i:i+2],16) for i in (1,3,5))
    return presets.get(bg_color,(255,255,255))

# ---------------- FINAL PIPELINE ----------------
def amazon_ready_image(img_bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    img = smart_crop_rgba(img)
    img = remove_reflection(img)
    img = auto_white_balance(img)

    CANVAS = 2000
    target = int(CANVAS * 0.9)

    w,h = img.size
    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA",(CANVAS,CANVAS),(*bg_rgb,255))

    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    background.paste(img,(x,y),img)

    if add_shadow == 1:
        shadow = background.point(lambda p: p*0.25)
        background = Image.blend(background, shadow, 0.15)

    background = background.convert("RGB")
    background = ImageEnhance.Sharpness(background).enhance(1.25)
    background = enhance(background)

    out = io.BytesIO()
    background.save(out,"JPEG",quality=98,optimize=True,subsampling=0)

    return out.getvalue()

# ---------------- BYTE LIMIT ----------------
def compress_to_limit(img_bytes, max_kb=9000):
    img = Image.open(io.BytesIO(img_bytes))
    q = 98
    while True:
        buf = io.BytesIO()
        img.save(buf,"JPEG",quality=q,optimize=True)
        size_kb = len(buf.getvalue())/1024
        if size_kb <= max_kb or q<=70:
            return buf.getvalue()
        q -= 2

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg_safe(image_bytes)
    final = amazon_ready_image(transparent, bg_color, add_shadow)
    final = compress_to_limit(final)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg_safe(image_bytes)
    final = amazon_ready_image(transparent, bg_color, add_shadow)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- VALIDATE ----------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    w,h = img.size
    return {"square": w==h, "resolution_ok": w>=1600}

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            transparent = remove_bg_safe(img_bytes)
            final = amazon_ready_image(transparent)
            final = compress_to_limit(final)
            zipf.writestr(f"amazon_{f.filename}",final)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )

