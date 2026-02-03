from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")


@app.get("/")
def root():
    return {"status": "ok"}


def remove_background(image_bytes: bytes) -> bytes:
    # Lazy import (VERY IMPORTANT for Railway)
    from rembg import remove
    return remove(image_bytes)


def process_for_amazon(image_bytes: bytes, canvas_size=2000) -> bytes:
    # 1️⃣ Remove background (AI)
    bg_removed = remove_background(image_bytes)

    img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")

    # 2️⃣ Crop to product
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # 3️⃣ Amazon 70% rule
    target = int(canvas_size * 0.7)
    w, h = img.size
    scale = target / max(w, h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # 4️⃣ Pure white background
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    x = (canvas_size - img.width) // 2
    y = (canvas_size - img.height) // 2
    canvas.paste(img, (x, y), img)

    # 5️⃣ Final JPEG
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=95, subsampling=0)
    out.seek(0)
    return out.read()


@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    data = await file.read()
    result = process_for_amazon(data)
    return StreamingResponse(io.BytesIO(result), media_type="image/jpeg")


@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    data = await file.read()
    result = process_for_amazon(data)
    return StreamingResponse(
        io.BytesIO(result),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=amazon_{file.filename}"}
    )
