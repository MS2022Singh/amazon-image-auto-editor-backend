from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")

@app.get("/")
def root():
    return {"status": "ok"}


def place_on_white_canvas(image_bytes: bytes, canvas_size=2000) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # --- PRODUCT MASK ---
    gray = img.convert("L")
    bw = gray.point(lambda x: 255 if x < 245 else 0, '1')  # product = white

    bbox = bw.getbbox()
    if bbox:
        img = img.crop(bbox)
        bw = bw.crop(bbox)

    # --- SCALE (Amazon safe 70%) ---
    target = int(canvas_size * 0.7)
    w, h = img.size
    scale = target / max(w, h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    bw = bw.resize(img.size, Image.NEAREST)

    # --- PURE WHITE CANVAS ---
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    x = (canvas_size - img.width) // 2
    y = (canvas_size - img.height) // 2

    # --- FORCE PURE WHITE BACKGROUND ---
    img_rgb = img.convert("RGB")
    canvas_px = canvas.load()
    img_px = img_rgb.load()
    mask_px = bw.load()

    for iy in range(img.height):
        for ix in range(img.width):
            if mask_px[ix, iy]:  # product pixel
                canvas_px[x + ix, y + iy] = img_px[ix, iy]
            # else: background stays 255,255,255

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95, subsampling=0)
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
