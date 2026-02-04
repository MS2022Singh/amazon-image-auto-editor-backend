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
    file: UploadFile = File(...),
    bg_color: str = "#FFFFFF"
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

