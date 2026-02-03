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


