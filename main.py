from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter

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

def gradient_background(size=(2000,2000), start=(255,255,255), end=(230,230,230)):
    base = Image.new("RGB", size, start)
    top = Image.new("RGB", size, end)
    mask = Image.linear_gradient("L").resize(size)
    return Image.composite(top, base, mask)


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

    img = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    # MAIN
    outputs["01_main.jpg"] = amazon_ready_image(transparent_bytes)

    # ZOOM
    zoom = img.resize((1800,1800), Image.LANCZOS)
    canvas = Image.new("RGB",(2000,2000),(255,255,255))
    canvas.paste(zoom,(100,100),zoom)
    buf = io.BytesIO()
    canvas.save(buf,"JPEG",quality=95)
    outputs["02_zoom.jpg"] = buf.getvalue()

    # CUT
    buf2 = io.BytesIO()
    img.convert("RGB").save(buf2,"JPEG",quality=95)
    outputs["03_cut.jpg"] = buf2.getvalue()

    # GRADIENT
    grad = gradient_background()
    grad.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    gbuf = io.BytesIO()
    grad.save(gbuf,"JPEG",quality=95)
    outputs["04_gradient.jpg"] = gbuf.getvalue()

    # SOFT LIFESTYLE
    life = Image.new("RGB",(2000,2000),(245,245,245))
    life.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    lbuf = io.BytesIO()
    life.save(lbuf,"JPEG",quality=95)
    outputs["05_soft.jpg"] = lbuf.getvalue()

    # DARK CONTRAST
    dark = Image.new("RGB",(2000,2000),(40,40,40))
    dark.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    dbuf = io.BytesIO()
    dark.save(dbuf,"JPEG",quality=95)
    outputs["06_dark.jpg"] = dbuf.getvalue()

    # BANNER SPACE
    banner = Image.new("RGB",(2000,2000),(255,255,255))
    banner.paste(img.resize((1200,1200),Image.LANCZOS),(400,400),img.resize((1200,1200),Image.LANCZOS))
    bbuf = io.BytesIO()
    banner.save(bbuf,"JPEG",quality=95)
    outputs["07_banner.jpg"] = bbuf.getvalue()

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
    background = amazon_smart_framing(img)

    if add_shadow == 1:
        background = apply_shadow(background)

    background = enhance_image(background)

    out = io.BytesIO()
    background = studio_lighting_correction(background)
background.convert("RGB").save(out,"JPEG",quality=95)

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

def amazon_smart_framing(img: Image.Image, canvas=2000, fill=0.90):

    img = smart_crop_rgba(img)

    w, h = img.size
    target = int(canvas * fill)

    scale = min(target / w, target / h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    background = Image.new("RGBA", (canvas, canvas), (255,255,255,255))

    x = (canvas - img.width)//2
    y = (canvas - img.height)//2

    background.paste(img, (x,y), img)

    return background.convert("RGB")

def studio_lighting_correction(img: Image.Image) -> Image.Image:

    # Mild brightness lift
    brightness = ImageEnhance.Brightness(img)
    img = brightness.enhance(1.04)

    # Contrast adjustment
    contrast = ImageEnhance.Contrast(img)
    img = contrast.enhance(1.10)

    # Slight color boost
    color = ImageEnhance.Color(img)
    img = color.enhance(1.05)

    # Sharpen
    sharp = ImageEnhance.Sharpness(img)
    img = sharp.enhance(1.15)

    # Very light micro-smooth
    img = img.filter(ImageFilter.SMOOTH)

    return img
