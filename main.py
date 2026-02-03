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

    # Detect product area
    gray = img.convert("L")
    bw = gray.point(lambda x: 0 if x > 245 else 255, '1')

    bbox = bw.getbbox()
    if bbox:
        img = img.crop(bbox)

    # --- SCALE CONTROL (70% rule) ---
    target_size = int(canvas_size * 0.7)
    w, h = img.size
    scale = target_size / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # White canvas
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # Center paste
    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2
    canvas.paste(img, (x, y), img)

    # Final JPEG
    final = canvas.convert("RGB")
    out = io.BytesIO()
    final.save(out, format="JPEG", quality=95)
    out.seek(0)

    return out.read()



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


