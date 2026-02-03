from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")


@app.get("/")
def root():
    return {"status": "ok"}


# ==============================
# CORE IMAGE PROCESSING FUNCTION
# ==============================
def process_for_amazon(image_bytes: bytes, canvas_size: int = 2000) -> bytes:
    """
    1. Remove background completely
    2. Keep only product
    3. Place on pure white canvas
    4. Amazon 70% size rule
    """

    # Load image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # ------------------------------
    # STEP 1: TRUE BACKGROUND REMOVAL
    # ------------------------------
    gray = img.convert("L")

    # Product = white (255), Background = black (0)
    mask = gray.point(lambda x: 255 if x < 245 else 0)

    # Apply transparency
    img.putalpha(mask)

    # Crop to product bounds
    bbox = mask.getbbox()
    if bbox:
        img = img.crop(bbox)

    # ------------------------------
    # STEP 2: AMAZON SCALE (70%)
    # ------------------------------
    target_size = int(canvas_size * 0.7)
    w, h = img.size
    scale = target_size / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # ------------------------------
    # STEP 3: PURE WHITE CANVAS
    # ------------------------------
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2

    # Paste using alpha mask (clean edges)
    canvas.paste(img, (x, y), img)

    # ------------------------------
    # STEP 4: FINAL JPEG EXPORT
    # ------------------------------
    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
    out.seek(0)

    return out.read()


# ==================
# PREVIEW ENDPOINT
# ==================
@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    processed = process_for_amazon(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg"
    )


# ==================
# DOWNLOAD ENDPOINT
# ==================
@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    processed = process_for_amazon(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )
