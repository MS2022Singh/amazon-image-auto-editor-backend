from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

try:
    from PIL import ImageFilter
    FILTER_AVAILABLE = True
except:
    FILTER_AVAILABLE = False


app = FastAPI(title="Amazon Image Auto Editor")


@app.get("/")
def root():
    return {"status": "ok"}


def soften_shadow(img: Image.Image) -> Image.Image:
    if not FILTER_AVAILABLE:
        return img
    shadow = img.filter(ImageFilter.GaussianBlur(radius=2))
    shadow = shadow.point(lambda p: min(255, int(p * 1.08)))
    return shadow


def place_on_white_canvas(image_bytes: bytes, canvas_size=2000) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Detect product
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x > 245 else 255, "1")
    bbox = bw.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Scale (70%)
    target = int(canvas_size * 0.7)
    w, h = img.size
    scale = target / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    shadow = soften_shadow(img.copy())

    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2

    canvas.paste(shadow, (x + 6, y + 6), shadow)
    canvas.paste(img, (x, y), img)

    final = canvas.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95)
    out.seek(0)
    return out.read()


@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type=file.content_type
    )


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
