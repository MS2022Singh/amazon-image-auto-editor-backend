from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import requests, io, os
from PIL import Image, ImageEnhance

app = FastAPI(title="Amazon Image Auto Editor")

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")


@app.get("/")
def root():
    return {"status": "ok"}


# -----------------------------
# REMOVE.BG
# -----------------------------
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

    return response.content  # transparent PNG

def compose_shadow_free_white(product_rgba: Image.Image, canvas=2000) -> Image.Image:
    # Step 1: pure white canvas
    bg = Image.new("RGBA", (canvas, canvas), (255, 255, 255, 255))

    # Step 2: center placement
    pw, ph = product_rgba.size
    scale = min(canvas * 0.85 / pw, canvas * 0.85 / ph)
    new_size = (int(pw * scale), int(ph * scale))
    product = product_rgba.resize(new_size, Image.LANCZOS)

    x = (canvas - new_size[0]) // 2
    y = (canvas - new_size[1]) // 2

    # Step 3: HARD alpha cleanup (kills shadow)
    r, g, b, a = product.split()
    a = a.point(lambda p: 255 if p > 200 else 0)

    product = Image.merge("RGBA", (r, g, b, a))

    # Step 4: paste without shadow bleed
    bg.paste(product, (x, y), product)

    return bg.convert("RGB")

# -----------------------------
# BACKGROUND PRESETS
# -----------------------------
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


# -----------------------------
# SMART ZOOM CALCULATION
# -----------------------------
def calculate_fill_ratio(img: Image.Image) -> float:
    alpha = img.split()[-1]
    non_empty = sum(1 for p in alpha.getdata() if p > 10)
    total = alpha.width * alpha.height

    coverage = non_empty / total

    if coverage < 0.10:
        return 0.92
    elif coverage < 0.20:
        return 0.88
    elif coverage < 0.35:
        return 0.82
    else:
        return 0.75


# -----------------------------
# AMAZON READY IMAGE
# -----------------------------
def amazon_ready_image(
    transparent_bytes: bytes,
    canvas_size: int = 2000,
    bg_color: str = "#FFFFFF"
) -> bytes:
    product = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")

    # Create background
    if bg_color.startswith("#"):
        bg_color = bg_color.lstrip("#")
        r, g, b = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))
        background = Image.new("RGBA", (canvas_size, canvas_size), (r, g, b, 255))
    else:
        background = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # Resize product (Amazon ~85% rule)
    max_size = int(canvas_size * 0.85)
    product.thumbnail((max_size, max_size), Image.LANCZOS)

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2

    background.paste(product, (x, y), product)

    final = background.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95)
    out.seek(0)

    return out.read()

def validate_amazon_image(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size

    errors = []
    warnings = []

    # Size checks
    if width < 1000 or height < 1000:
        errors.append("Image size too small (min 1000x1000 required)")

    if width != height:
        errors.append("Image must be square")

    # Background check (corner pixel)
    pixel = img.getpixel((5, 5))
    if pixel[:3] != (255, 255, 255):
        warnings.append("Background is not pure white (#FFFFFF)")

    # Product coverage estimation
    non_white = sum(
        1 for p in img.getdata()
        if p[:3] != (255, 255, 255)
    )
    coverage = non_white / (width * height)

    if coverage < 0.75:
        warnings.append("Product appears too small in frame")

    return {
        "status": "fail" if errors else "pass",
        "errors": errors,
        "warnings": warnings,
        "size": f"{width}x{height}",
        "coverage_estimate": round(coverage * 100, 2)
    }

def validate_amazon_image(img: Image.Image) -> dict:
    width, height = img.size

    # Rule 1: size
    if width < 1000 or height < 1000:
        return {"valid": False, "reason": "Image size below 1000x1000"}

    # Rule 2: background purity
    pixels = img.load()
    white_pixels = 0
    total_pixels = width * height

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            if r > 250 and g > 250 and b > 250:
                white_pixels += 1

    white_ratio = white_pixels / total_pixels

    if white_ratio < 0.85:
        return {"valid": False, "reason": "Background not pure white"}

    return {
        "valid": True,
        "message": "Amazon compliant main image"
    }

@app.post("/process/validate")
async def validate_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    report = validate_amazon_image(img)
    return report

def force_pure_white_background(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")

    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            # Shadow / gray detection
            if a < 255 or (r < 245 or g < 245 or b < 245):
                pixels[x, y] = (255, 255, 255, 255)

    return img

def auto_fix_amazon_image(image_bytes: bytes, canvas_size=2000) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Remove transparency on white
    img = force_pure_white_background(img)

    # Crop product area (non-white)
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x > 245 else 255, "1")
    bbox = bw.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Resize product to 85% of canvas
    target = int(canvas_size * 0.85)
    img.thumbnail((target, target), Image.LANCZOS)

    # Create final canvas
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    x = (canvas_size - img.width) // 2
    y = (canvas_size - img.height) // 2
    canvas.paste(img, (x, y))

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()

# -----------------------------
# PREVIEW (NO DOWNLOAD)
# -----------------------------
@app.post("/process/preview")
async def preview_image(
    file: UploadFile = File(...),
    bg_color: str = "#FFFFFF"
):
    image_bytes = await file.read()

    transparent = remove_bg(image_bytes)
    preview = amazon_ready_image(
        transparent,
        canvas_size=1200,
        bg_color=bg_color
    )

    return StreamingResponse(
        io.BytesIO(preview),
        media_type="image/jpeg"
    )

# -----------------------------
# AMAZON FINAL DOWNLOAD
# -----------------------------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...)
):
    image_bytes = await file.read()

    report = validate_amazon_image(image_bytes)

    if report["status"] == "fail" or report["warnings"]:
        final_image = auto_fix_amazon_image(image_bytes)
    else:
        final_image = image_bytes

    return StreamingResponse(
        io.BytesIO(final_image),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )
transparent = remove_bg(image_bytes)

img_rgba = Image.open(io.BytesIO(transparent)).convert("RGBA")

final_img = compose_shadow_free_white(img_rgba)

def amazon_validator(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size

    # square check
    square = w == h

    # resolution
    resolution_ok = w >= 1600 and h >= 1600

    # background check (sample corners)
    pixels = img.load()
    corners = [
        pixels[0, 0],
        pixels[w-1, 0],
        pixels[0, h-1],
        pixels[w-1, h-1],
    ]
    background_white = all(
        abs(r-255) < 3 and abs(g-255) < 3 and abs(b-255) < 3
        for r, g, b in corners
    )

    amazon_safe = square and resolution_ok and background_white

    warnings = []
    if not square:
        warnings.append("Image is not square")
    if not resolution_ok:
        warnings.append("Resolution below 1600x1600")
    if not background_white:
        warnings.append("Background is not pure white")

    return {
        "square": square,
        "resolution_ok": resolution_ok,
        "background_white": background_white,
        "amazon_safe": amazon_safe,
        "warnings": warnings,
    }

@app.post("/process/validate")
async def validate_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    report = amazon_validator(image_bytes)
    return report

import zipfile
from fastapi.responses import StreamingResponse

@app.post("/process/batch")
async def process_batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            image_bytes = await file.read()

            transparent = remove_bg(image_bytes)
            final_image = amazon_ready_image(transparent)

            zipf.writestr(
                f"amazon_{file.filename}",
                final_image
            )

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=amazon_images.zip"
        }
    )






