from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import requests, io, os
from PIL import Image

app = FastAPI(title="Amazon Image Auto Editor")

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")


@app.get("/")
def root():
    return {"status": "ok"}


def remove_bg(image_bytes: bytes) -> bytes:
    if not REMOVEBG_API_KEY:
        raise RuntimeError("Remove.bg API key missing")

    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(f"remove.bg failed: {response.text}")

    return response.content  # PNG with transparency


from PIL import Image, ImageEnhance, ImageFilter
import io

def amazon_ready_image(
    transparent_bytes: bytes,
    canvas_size: int = 2000,
    fill_ratio: float = 0.88,   # 88% product coverage
    sharpen: float = 1.15,      # subtle DSLR sharpness
    contrast: float = 1.05
) -> bytes:

    product = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")

    # --- Trim empty transparency ---
    bbox = product.getbbox()
    if bbox:
        product = product.crop(bbox)

    # --- Resize to fill Amazon frame ---
    max_size = int(canvas_size * fill_ratio)
    product.thumbnail((max_size, max_size), Image.LANCZOS)

    # --- White canvas ---
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2
    canvas.paste(product, (x, y), product)

    final = canvas.convert("RGB")

    # --- Pro polish ---
    final = ImageEnhance.Sharpness(final).enhance(sharpen)
    final = ImageEnhance.Contrast(final).enhance(contrast)

    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()

def calculate_fill_ratio(img: Image.Image) -> float:
    """
    Returns how much % of image is actual product (non-transparent)
    """
    alpha = img.split()[-1]
    non_empty = sum(1 for p in alpha.getdata() if p > 10)
    total = alpha.width * alpha.height

    coverage = non_empty / total

    # Smart clamps (Amazon-safe)
    if coverage < 0.10:
        return 0.92   # very small product → zoom more
    elif coverage < 0.20:
        return 0.88
    elif coverage < 0.35:
        return 0.82
    else:
        return 0.75   # big product → less zoom

@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    transparent = preview = remove_bg(image_bytes)
    final_image = amazon_ready_image(transparent)

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg"
    )

@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    try:
        transparent_png = remove_bg(image_bytes)
        final_image = amazon_ready_image(transparent_png)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        },
    )

def amazon_ready_image(
    transparent_bytes: bytes,
    canvas_size: int = 2000,
    background: str = "white"
) -> bytes:
    
    product = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")

    bbox = product.getbbox()
    if bbox:
        product = product.crop(bbox)

    pw, ph = product.size

    # AUTO ZOOM DECISION
    fill_ratio = calculate_fill_ratio(product)

    max_side = int(canvas_size * fill_ratio)
    product.thumbnail((max_size, max_size), Image.LANCZOS)

     bg_color = resolve_background(background)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), bg_color)

    scale = min(max_side / pw, max_side / ph)

    new_size = (int(pw * scale), int(ph * scale))
    product = product.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2

    canvas.paste(product, (x, y), product)

    final = canvas.convert("RGB")
    final = ImageEnhance.Sharpness(final).enhance(1.15)
    final = ImageEnhance.Contrast(final).enhance(1.05)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()

def resolve_background(bg: str):
    presets = {
        "white": (255, 255, 255, 255),
        "offwhite": (245, 245, 245, 255),
        "lightgrey": (240, 240, 240, 255),
    }

    if bg.startswith("#") and len(bg) == 7:
        r = int(bg[1:3], 16)
        g = int(bg[3:5], 16)
        b = int(bg[5:7], 16)
        return (r, g, b, 255)

    return presets.get(bg, (255, 255, 255, 255))

@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    final_image = amazon_ready_image(
        transparent,
        background="white"   # 🔒 locked for Amazon
    )

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg"
    )


@app.post("/process/preview")
async def preview_image(
    file: UploadFile = File(...),
    bg: str = "white"
):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)

    final_image = amazon_ready_image(
        transparent,
        background=bg
    )

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg"
    )


    # ⚠️ No Content-Disposition here
    # so browser / Swagger can SHOW the image
    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg"
    )




