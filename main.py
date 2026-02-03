from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter
import io

app = FastAPI(title="Amazon Image Auto Editor")


@app.get("/")
def root():
    return {"status": "ok"}


# ---------------- HELPER FUNCTIONS ---------------- #

def soften_shadow(img: Image.Image) -> Image.Image:
    """
    Very light softening to avoid harsh shadows.
    Does NOT change product shape.
    """
    shadow = img.copy()
    shadow = shadow.point(lambda p: min(255, int(p * 1.1)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
    return shadow


def neutralize_background(img: Image.Image, mask: Image.Image) -> Image.Image:
    """
    img  : RGBA image
    mask : product mask (white = product, black = background)
    Only background is neutralized, product untouched.
    """
    img = img.convert("RGB")
    pixels = img.load()
    mask_px = mask.load()

    w, h = img.size
    for y in range(h):
        for x in range(w):
            if mask_px[x, y] == 0:  # background pixel
                r, g, b = pixels[x, y]
                avg = (r + g + b) // 3
                pixels[x, y] = (avg, avg, avg)

    return img


# ---------------- MAIN PROCESSOR ---------------- #

def place_on_white_canvas(image_bytes: bytes, canvas_size: int = 2000) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Create product mask
    gray = img.convert("L")
    mask = gray.point(lambda x: 0 if x > 245 else 255, "1")

    bbox = mask.getbbox()
    if bbox:
        img = img.crop(bbox)
        mask = mask.crop(bbox)

    # Neutralize background BEFORE canvas
    img = neutralize_background(img, mask)

    # ---- SCALE CONTROL (Amazon 70% rule) ----
    target_size = int(canvas_size * 0.7)
    w, h = img.size
    scale = target_size / max(w, h)
    img = img.resize(
        (int(w * scale), int(h * scale)),
        Image.LANCZOS
    )

    # White canvas
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # Center paste
    x = (canvas_size - img.width) // 2
    y = (canvas_size - img.height) // 2
    canvas.paste(img, (x, y), img)

    # Optional soft shadow smoothing
    canvas = soften_shadow(canvas)

    # Final JPEG
    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=95)
    out.seek(0)

    return out.read()


# ---------------- API ENDPOINTS ---------------- #

@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    processed = place_on_white_canvas(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg"
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
