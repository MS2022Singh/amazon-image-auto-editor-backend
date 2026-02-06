from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import requests, io, os, zipfile
from PIL import Image
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok"}

# -----------------------------
# REMOVE.BG
# -----------------------------
def remove_bg(image_bytes: bytes) -> bytes:
    if not REMOVEBG_API_KEY:
        raise RuntimeError("Remove.bg API key missing")

    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
        timeout=30
    )

    if r.status_code != 200:
        raise RuntimeError(r.text)

    return r.content  # transparent PNG

def resolve_background(bg_color: str):
    presets = {
        "white": (255, 255, 255, 255),
        "offwhite": (245, 245, 245, 255),
        "lightgrey": (240, 240, 240, 255),
        "black": (0, 0, 0, 255),
    }

    if not bg_color:
        return (255, 255, 255, 255)

    bg_color = bg_color.lower()

    # HEX color support
    if bg_color.startswith("#") and len(bg_color) == 7:
        r = int(bg_color[1:3], 16)
        g = int(bg_color[3:5], 16)
        b = int(bg_color[5:7], 16)
        return (r, g, b, 255)

    return presets.get(bg_color, (255, 255, 255, 255))

def smart_crop_rgba(img: Image.Image) -> Image.Image:
    """
    Crop image to visible (non-transparent) product area
    """
    alpha = img.split()[-1]

    # Convert alpha to binary mask
    mask = alpha.point(lambda p: 255 if p > 10 else 0)

    bbox = mask.getbbox()
    if bbox:
        return img.crop(bbox)

    return img

def amazon_ready_image(
    transparent_bytes: bytes,
    canvas_size: int = 2000,
    fill_ratio: float = 0.88,   # sweet spot for Amazon
    bg_color: str = "white"
) -> bytes:

    product = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")

    # STEP 1: smart crop (kills floating feel)
    product = smart_crop_rgba(product)

    # STEP 2: create pure background
    bg_rgba = resolve_background(bg_color)
    background = Image.new("RGBA", (canvas_size, canvas_size), bg_rgba (255, 255, 255, 255))

    # STEP 3: auto scale
    pw, ph = product.size
    max_dim = int(canvas_size * fill_ratio)
    scale = min(max_dim / pw, max_dim / ph)
    new_size = (int(pw * scale), int(ph * scale))
    product = product.resize(new_size, Image.LANCZOS)

    # STEP 4: center paste
    x = (canvas_size - new_size[0]) // 2
    y = (canvas_size - new_size[1]) // 2
    bg.paste(product, (x, y), product)

    final = bg.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)
    return out.read()

# -----------------------------
# SHADOW FREE AMAZON COMPOSE
# -----------------------------
def compose_shadow_free_white(product_rgba: Image.Image, canvas=2000) -> Image.Image:
    # 1️⃣ Smart crop first
    product_rgba = smart_crop_rgba(product_rgba)

    # 2️⃣ Create white canvas
    bg = Image.new("RGBA", (canvas, canvas), (255, 255, 255, 255))

    # 3️⃣ Resize product (slightly more aggressive for jewellery)
    pw, ph = product_rgba.size
    scale = min(canvas * 0.90 / pw, canvas * 0.90 / ph)
    product = product_rgba.resize(
        (int(pw * scale), int(ph * scale)), Image.LANCZOS
    )

    # 4️⃣ HARD alpha cleanup (kill shadows completely)
    r, g, b, a = product.split()
    a = a.point(lambda p: 255 if p > 200 else 0)
    product = Image.merge("RGBA", (r, g, b, a))

    # 5️⃣ Center placement
    x = (canvas - product.width) // 2
    y = (canvas - product.height) // 2
    bg.paste(product, (x, y), product)

    return bg.convert("RGB")

# -----------------------------
# AMAZON PIPELINE
# -----------------------------
def amazon_process(image_bytes: bytes, canvas=2000) -> bytes:
    transparent = remove_bg(image_bytes)
    product = Image.open(io.BytesIO(transparent)).convert("RGBA")
    final = compose_shadow_free_white(product, canvas)

    out = io.BytesIO()
    final.save(out, "JPEG", quality=95, subsampling=0)
    out.seek(0)
    return out.read()

# -----------------------------
# AMAZON VALIDATOR
# -----------------------------
def amazon_validator(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size

    corners = [
        img.getpixel((0, 0)),
        img.getpixel((w-1, 0)),
        img.getpixel((0, h-1)),
        img.getpixel((w-1, h-1)),
    ]

    background_white = all(
        abs(r-255) < 3 and abs(g-255) < 3 and abs(b-255) < 3
        for r, g, b in corners
    )

    return {
        "square": w == h,
        "resolution_ok": w >= 1600,
        "background_white": background_white,
        "amazon_safe": w == h and w >= 1600 and background_white
    }

# -----------------------------
# PREVIEW
# -----------------------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    preview = amazon_process(image_bytes, canvas=1200)

    return StreamingResponse(io.BytesIO(preview), media_type="image/jpeg")

# -----------------------------
# FINAL DOWNLOAD
# -----------------------------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = "white"
):
    image_bytes = await file.read()

    transparent = remove_bg(image_bytes)
    final_image = amazon_ready_image(
        transparent,
        bg_color=bg_color
    )

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )

# -----------------------------
# VALIDATE
# -----------------------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return amazon_validator(image_bytes)

# -----------------------------
# BATCH
# -----------------------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for file in files:
            img_bytes = await file.read()
            final = amazon_process(img_bytes)
            zipf.writestr(f"amazon_{file.filename}", final)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=amazon_images.zip"}
    )




