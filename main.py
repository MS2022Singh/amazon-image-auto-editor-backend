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


def amazon_ready_image(png_bytes: bytes, canvas_size=2000) -> bytes:
    product = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # PURE WHITE CANVAS
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    # Resize product (Amazon rule: product ~85% frame)
    max_size = int(canvas_size * 0.85)
    product.thumbnail((max_size, max_size), Image.LANCZOS)

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2

    # Paste WITHOUT shadow
    canvas.paste(product, (x, y), product)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()

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
    category: str = "jewellery"
) -> bytes:
    product = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")

    pw, ph = product.size

    # Category-based fill ratio
    CATEGORY_FILL = {
        "jewellery": 0.60,   # small products
        "watch": 0.65,
        "shoe": 0.80,
        "bag": 0.85,
        "default": 0.85
    }

    fill_ratio = CATEGORY_FILL.get(category, CATEGORY_FILL["default"])

    max_side = int(canvas_size * fill_ratio)

    scale = min(max_side / pw, max_side / ph)

    new_size = (int(pw * scale), int(ph * scale))
    product = product.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2

    canvas.paste(product, (x, y), product)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()


