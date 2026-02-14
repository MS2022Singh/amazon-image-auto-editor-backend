from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter
from rembg import remove

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "Amazon Image Auto Editor running"}

# ---------------- ENV TEST ----------------
@app.get("/envtest")
def envtest():
    return {"ok": True}

# ---------------- INTERNAL WHITE BG ----------------
def internal_white_bg(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    white_bg = Image.new("RGBA", img.size, (255,255,255,255))
    white_bg.paste(img,(0,0),img)

    out = io.BytesIO()
    white_bg.convert("RGB").save(out,"JPEG",quality=95)
    return out.getvalue()

# ---------------- SAFE BG REMOVE ----------------
def remove_bg_safe(image_bytes):
    try:
        result = remove(image_bytes)
        if not result or len(result) < 1000:
            return internal_white_bg(image_bytes)
        return result
    except:
        return internal_white_bg(image_bytes)

# ---------------- HELPERS ----------------
def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    return img

def resolve_background(bg_color):
    presets = {
        "white": (255,255,255),
        "black": (0,0,0),
        "lightgrey": (240,240,240)
    }
    return presets.get(bg_color,(255,255,255))

# ---------------- PIPELINE ----------------
def process_pipeline(img_bytes, bg_color="white", add_shadow=0):

    transparent = remove_bg_safe(img_bytes)
    img = Image.open(io.BytesIO(transparent)).convert("RGBA")

    CANVAS = 2000
    target = int(CANVAS*0.9)

    w,h = img.size
    if w == 0 or h == 0:
        return internal_white_bg(img_bytes)

    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA",(CANVAS,CANVAS),(*bg_rgb,255))

    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    background.paste(img,(x,y),img)

    if add_shadow == 1:
        shadow = background.filter(ImageFilter.GaussianBlur(35))
        background = Image.blend(background, shadow, 0.15)

    background = enhance(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95,optimize=True)
    return out.getvalue()

# ---------------- SIZE LIMIT ----------------
def compress_to_limit(img_bytes, max_kb=9000):
    img = Image.open(io.BytesIO(img_bytes))
    q = 95
    while True:
        buf = io.BytesIO()
        img.save(buf,"JPEG",quality=q,optimize=True)
        if len(buf.getvalue())/1024 <= max_kb or q <= 70:
            return buf.getvalue()
        q -= 2

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(file: UploadFile = File(...), bg_color: str = Form("white"), add_shadow: int = Form(0)):
    image_bytes = await file.read()
    final = process_pipeline(image_bytes, bg_color, add_shadow)
    final = compress_to_limit(final)
    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...), bg_color: str = Form("white"), add_shadow: int = Form(0)):
    image_bytes = await file.read()
    final = process_pipeline(image_bytes, bg_color, add_shadow)
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
            final = process_pipeline(img_bytes)
            zipf.writestr(f"amazon_{f.filename}",final)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"})
