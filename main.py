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

# ---------------- HELPERS ----------------
def resolve_background(bg_color: str):
    presets = {
        "white": (255,255,255),
        "offwhite": (245,245,245),
        "lightgrey": (240,240,240),
        "black": (0,0,0),
    }
    if bg_color.startswith("#"):
        return tuple(int(bg_color[i:i+2],16) for i in (1,3,5))
    return presets.get(bg_color,(255,255,255))

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

def amazon_smart_framing(img, canvas=2000, fill=0.90):
    img = smart_crop_rgba(img)

    w,h = img.size
    target = int(canvas*fill)
    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg = Image.new("RGBA",(canvas,canvas),(255,255,255,255))
    x = (canvas-img.width)//2
    y = (canvas-img.height)//2
    bg.paste(img,(x,y),img)

    return bg

def auto_amazon_fix(image_bytes: bytes):

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    CANVAS = 2000
    target = int(CANVAS * 0.90)

    # crop transparent
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)

    # resize
    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # white background
    bg = Image.new("RGBA", (CANVAS, CANVAS), (255,255,255,255))
    x = (CANVAS - img.width)//2
    y = (CANVAS - img.height)//2
    bg.paste(img,(x,y),img)

    out = io.BytesIO()
    bg.convert("RGB").save(out,"JPEG",quality=95)

    return out.getvalue()

# ---------------- AMAZON READY ----------------
def amazon_ready_image(img_bytes: bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    framed = amazon_smart_framing(img)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA", framed.size, (*bg_rgb,255))
    background.paste(framed,(0,0),framed)

    if add_shadow == 1:
        shadow = framed.point(lambda p: p*0.3)
        background.paste(shadow,(0,0),shadow)

    background = studio_lighting_correction(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95)
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
    final = amazon_ready_image(transparent,bg_color,add_shadow)

    return StreamingResponse(
        io.BytesIO(final),
        media_type="image/jpeg",
        headers={"Content-Disposition":f"attachment; filename=amazon_{file.filename}"}
    )

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)
    return StreamingResponse(io.BytesIO(final),media_type="image/jpeg")

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
            transparent = remove_bg(img_bytes)
            final = amazon_ready_image(transparent)
            zipf.writestr(f"amazon_{f.filename}",final)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )

@app.post("/process/auto-fix")
async def auto_fix(file: UploadFile = File(...)):
    image_bytes = await file.read()

    transparent = remove_bg(image_bytes)
    fixed = auto_amazon_fix(transparent)

    return StreamingResponse(
        io.BytesIO(fixed),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=fixed_{file.filename}"}
    )
