from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter

app = FastAPI(title="Amazon Image Auto Editor")

# ---------------- CORS ----------------
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

# ---------------- BACKGROUND ----------------
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

# ---------------- CROP ----------------
def smart_crop_rgba(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

# ---------------- ENHANCE ----------------
def enhance_image(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(1.05)
    return img

# ---------------- LIGHTING ----------------
def studio_lighting_correction(img):
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = img.filter(ImageFilter.SMOOTH)
    return img

def reduce_reflections(img: Image.Image) -> Image.Image:

    # slight highlight compression
    img = ImageEnhance.Contrast(img).enhance(0.96)

    # micro smooth to reduce sharp light reflections
    img = img.filter(ImageFilter.SMOOTH_MORE)

    # restore clarity
    img = ImageEnhance.Sharpness(img).enhance(1.08)

    return img












def generate_listing_pack(transparent_bytes: bytes):

    img = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    outputs = {}

    # 1 MAIN
    outputs["01_main.jpg"] = amazon_ready_image(transparent_bytes)

    # 2 ZOOM
    zoom = img.resize((1800,1800), Image.LANCZOS)
    canvas = Image.new("RGB",(2000,2000),(255,255,255))
    canvas.paste(zoom,(100,100),zoom)
    buf = io.BytesIO()
    canvas.save(buf,"JPEG",quality=95)
    outputs["02_zoom.jpg"] = buf.getvalue()

    # 3 CUTOUT
    buf2 = io.BytesIO()
    img.convert("RGB").save(buf2,"JPEG",quality=95)
    outputs["03_cut.jpg"] = buf2.getvalue()

    # 4 GRADIENT
    grad = Image.new("RGB",(2000,2000),(245,245,245))
    grad.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    gbuf = io.BytesIO()
    grad.save(gbuf,"JPEG",quality=95)
    outputs["04_gradient.jpg"] = gbuf.getvalue()

    # 5 SOFT
    soft = Image.new("RGB",(2000,2000),(250,250,250))
    soft.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    sbuf = io.BytesIO()
    soft.save(sbuf,"JPEG",quality=95)
    outputs["05_soft.jpg"] = sbuf.getvalue()

    # 6 DARK
    dark = Image.new("RGB",(2000,2000),(40,40,40))
    dark.paste(img.resize((1500,1500),Image.LANCZOS),(250,250),img.resize((1500,1500),Image.LANCZOS))
    dbuf = io.BytesIO()
    dark.save(dbuf,"JPEG",quality=95)
    outputs["06_dark.jpg"] = dbuf.getvalue()

    # 7 BANNER
    banner = Image.new("RGB",(2000,2000),(255,255,255))
    banner.paste(img.resize((1200,1200),Image.LANCZOS),(400,400),img.resize((1200,1200),Image.LANCZOS))
    bbuf = io.BytesIO()
    banner.save(bbuf,"JPEG",quality=95)
    outputs["07_banner.jpg"] = bbuf.getvalue()

    return outputs

# ---------------- SHADOW ----------------
def apply_shadow(img):
    shadow = img.copy().convert("RGBA")
    shadow = shadow.point(lambda p: p * 0.3)
    return shadow

# ---------------- SMART FRAMING ----------------
def amazon_smart_framing(img: Image.Image, canvas=2000):

    # transparent crop
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Amazon ideal fill = 92%
    FILL_RATIO = 0.92
    target = int(canvas * FILL_RATIO)

    w, h = img.size
    scale = min(target / w, target / h)

    new_w = int(w * scale)
    new_h = int(h * scale)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    background = Image.new("RGBA", (canvas, canvas), (255, 255, 255, 255))

    x = (canvas - new_w) // 2
    y = (canvas - new_h) // 2

    background.paste(img, (x, y), img)

    return background


# ---------------- AMAZON READY ----------------
def amazon_ready_image(img_bytes: bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    background = amazon_smart_framing(img)

    if add_shadow == 1:
        background = apply_shadow(background)

    background = enhance_image(background)
    background = studio_lighting_correction(background.convert("RGB"))
    background = reduce_reflections(background)

    framed = amazon_smart_framing(img)

    out = io.BytesIO()
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
            zipf.writestr(f"amazon_{f.filename}", final)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )

@app.post("/process/listing-pack")
async def listing_pack(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    images = generate_listing_pack(transparent)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for name,data in images.items():
            zipf.writestr(name,data)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_listing_pack.zip"}
    )


