from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
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

# ---------------- INTERNAL WHITE BG ----------------
def internal_white_bg(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255,255,255,255))
    bg.paste(img,(0,0),img)

    out = io.BytesIO()
    bg.convert("RGB").save(out,"JPEG",quality=95)
    return out.getvalue()

# ---------------- REMOVE BG SAFE ----------------
def remove_bg_safe(image_bytes):
    try:
        output = remove(image_bytes)
        if not output:
            return internal_white_bg(image_bytes)
        return output
    except:
        return internal_white_bg(image_bytes)

# ---------------- HELPERS ----------------
def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    return img

def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

def resolve_background(bg_color):
    presets = {
        "white": (255,255,255),
        "black": (0,0,0),
        "lightgrey": (240,240,240)
    }
    return presets.get(bg_color,(255,255,255))

# ---------------- CORE ----------------
def process_pipeline(img_bytes, bg_color="white", add_shadow=0):

    transparent = remove_bg_safe(img_bytes)
    img = Image.open(io.BytesIO(transparent)).convert("RGBA")

    if img.width == 0 or img.height == 0:
        return internal_white_bg(img_bytes)

    img = auto_white_balance(img)

    CANVAS = 2000
    target = int(CANVAS*0.9)

    w,h = img.size
    scale = min(target/w, target/h)
    img = img.resize((int(w*scale),int(h*scale)),Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA",(CANVAS,CANVAS),(*bg_rgb,255))

    x=(CANVAS-img.width)//2
    y=(CANVAS-img.height)//2
    background.paste(img,(x,y),img)

    if add_shadow==1:
        shadow = background.filter(ImageFilter.GaussianBlur(35))
        background = Image.blend(background,shadow,0.15)

    background = enhance(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95,optimize=True)
    return out.getvalue()

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(file: UploadFile = File(...), bg_color: str = Form("white"), add_shadow: int = Form(0)):
    img_bytes = await file.read()
    final = process_pipeline(img_bytes,bg_color,add_shadow)
    return StreamingResponse(io.BytesIO(final),media_type="image/jpeg")

@app.post("/process/preview")
async def preview(file: UploadFile = File(...), bg_color: str = Form("white"), add_shadow: int = Form(0)):
    img_bytes = await file.read()
    final = process_pipeline(img_bytes,bg_color,add_shadow)
    return StreamingResponse(io.BytesIO(final),media_type="image/jpeg")

@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            final = process_pipeline(img_bytes)
            zipf.writestr(f.filename,final)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip")

