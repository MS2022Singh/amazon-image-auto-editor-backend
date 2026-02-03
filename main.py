from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")

@app.get("/")
def root():
    return {"status": "ok"}

def convert_to_white_background(image_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    white_bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    white_bg.paste(image, (0, 0), image)

    final_image = white_bg.convert("RGB")

    output = io.BytesIO()
    final_image.save(output, format="JPEG", quality=95)
    output.seek(0)

    return output.read()

@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    processed = convert_to_white_background(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg"
    )

@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    processed = convert_to_white_background(image_bytes)

    return StreamingResponse(
        io.BytesIO(processed),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=processed_{file.filename}"
        }
    )
