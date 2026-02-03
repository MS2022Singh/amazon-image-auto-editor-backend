from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter
import io

app = FastAPI(title="Amazon Image Auto Editor")


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "ok"}


# -------------------------
# SHADOW SOFTENER
# -------------------------
def soften_shadow(img: Image.Image) -> Image.Image:
    shadow = img.copy()
    shadow = shadow.point(lambda p: min(255, int(p * 1.15)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
    return shadow


# -------------------------
# BACKGROUND NEUTRALIZER
# -------------------------
def neutralize_background(img: Image.Image, mask: Image.Image) -> Image.Image:
    """
    img  : RGB image
    mask : product mask (white = product, black = background)
    """
    img = img.convert("RGB")
    pixels = img.load()
    mask_px = mask.load()

    w, h = img.size
    for y in range(h):
        for x in range(w):
            if mask_px[x, y] == 0:  # background
                r, g, b = pixels[x, y]
                avg = int((r + g + b) / 3)
                pixels[x, y] = (avg, avg, avg)

    return img


# -------------------------
# MAIN PIPELINE
# -------------------------
def place_on_white_canvas(image_bytes: bytes, canvas_size=2000) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # --- Detect product mask ---
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x > 245 else 255, "1")

    bbox = bw.getbbox()
    if bbox:
        img = img.crop(bbox)
        bw = bw.crop(bbox)

    # --- Neutralize background (before resize) ---
    img = neutralize_background(img, bw)

    # --- SCALE CONTROL (Amazon 70% rule) ---
    target_size = int(canvas_size * 0.7)
    w, h = img.size
    scale = target_size / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # --- White canvas ---
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # --- Center paste ---
    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2
    canvas.paste(img, (x, y), img)

    # --- Soften shadow AFTER paste ---
    canvas = soften_shadow(canvas)

    # --- Final JPEG ---
    final = canvas.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95)
    out.seek(0)

    return out.read()


# -------------------------
# PREVIEW (NO MODIFICATION)
# -------------------------
@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type=file.content_type
    )


# -------------------------
# FINAL AMAZON IMAGE
# -------------------------
@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    processed = place_on_white_canvas(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )
