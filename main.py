from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import requests
import io
import os
from PIL import Image

app = FastAPI(title="Amazon Image Auto Editor")

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

@app.get("/")
def root():
    return {"status": "ok"}

def remove_bg_with_api(image_bytes: bytes) -> bytes:
    if not REMOVEBG_API_KEY:
        raise RuntimeError("Remove.bg API key missing")

    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": image_bytes},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        timeout=60
    )

    if response.status_code != 200:
        raise RuntimeError(f"remove.bg failed: {response.text}")

    return response.content  # PNG with transparent bg


def prepare_amazon_image(png_bytes: bytes, canvas_size=2000) -> bytes:
    product = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # White background
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # Amazon recommends product ~85% of frame
    target = int(canvas_size * 0.85)
    product.thumbnail((target, target), Image.LANCZOS)

    x = (canvas_size - product.width) // 2
    y = (canvas_size - product.height) // 2

    canvas.paste(product, (x, y), product)

    final = canvas.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()


@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    return StreamingResponse(
        file.file,
        media_type=file.content_type
    )


@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    try:
        original = await file.read()
        cutout = remove_bg_with_api(original)
        final = prepare_amazon_image(cutout)

        return StreamingResponse(
            io.BytesIO(final),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
