from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter
import io

app = FastAPI(title="Amazon Image Auto Editor")


@app.get("/")
def root():
    return {"status": "ok"}


# -------------------------------------------------
# FORCE PURE WHITE BACKGROUND (AMAZON SAFE)
# -------------------------------------------------
def force_pure_white(img: Image.Image, mask: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    pixels = img.load()
    mask_px = mask.load()

    w, h = img.size
    for y in range(h):
        for x in range(w):
            if mask_px[x, y] == 0:  # background
                pixels[x, y] = (255, 255, 255)

    return img


# -------------------------------------------------
# OPTIONAL SOFT SHADOW (NON-AMAZON)
# -------------------------------------------------
def add_soft_shadow(canvas: Image.Image) -> Image.Image:
    shadow = canvas.copy().convert("L")
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))

    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 70))
    shadow_layer.putalpha(shadow)

    base = Image.new("RGBA", canvas.size, (255, 255, 255, 255))
    base = Image.alpha_composite(base, shadow_layer)
    base = Image.alpha_composite(base, canvas)

    return base


# -------------------------------------------------
# CORE PROCESSOR
# -------------------------------------------------
def place_on_white_canvas(
    image_bytes: bytes,
    canvas_size: int = 2000,
    shadow: bool = False
) -> bytes:

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # --- PRODUCT MASK ---
    gray = img.convert("L")
    mask = gray.point(lambda x: 255 if x < 245 else 0, "L")

    bbox = mask.getbbox()
    if bbox:
        img = img.crop(bbox)
        mask = mask.crop(bbox)

    # --- SCALE (70% RULE) ---
    target = int(canvas_size * 0.7)
    w, h = img.size
    scale = target / max(w, h)

    new_w = int(w * scale)
    new_h = int(h * scale)

    img = img.resize((new_w, new_h), Image.LANCZOS)
    mask = mask.resize((new_w, new_h), Image.LANCZOS)

    # --- WHITE CANVAS ---
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
    canvas_mask = Image.new("L", (canvas_size, canvas_size), 0)

    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2

    canvas.paste(img, (x, y), img)
    canvas_mask.paste(mask, (x, y))

    # --- FORCE PURE WHITE ---
    final = force_pure_white(canvas, canvas_mask)

    # --- OPTIONAL SHADOW ---
    if shadow:
        final = add_soft_shadow(final.convert("RGBA")).convert("RGB")

    # --- OUTPUT JPEG ---
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95)
    out.seek(0)

    return out.read()


# -------------------------------------------------
# PREVIEW (RAW IMAGE)
# -------------------------------------------------
@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    return StreamingResponse(
        io.BytesIO(await file.read()),
        media_type=file.content_type
    )


# -------------------------------------------------
# AMAZON SAFE ENDPOINT (NO SHADOW)
# -------------------------------------------------
@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    processed = place_on_white_canvas(
        await file.read(),
        shadow=False
    )
    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )


# -------------------------------------------------
# CUSTOM ENDPOINT (OPTIONAL SHADOW)
# -------------------------------------------------
@app.post("/process/custom")
async def process_custom_image(
    file: UploadFile = File(...),
    shadow: bool = False
):
    processed = place_on_white_canvas(
        await file.read(),
        shadow=shadow
    )
    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg"
    )
