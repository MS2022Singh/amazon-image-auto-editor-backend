from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")

@app.get("/")
def root():
    return {"status": "ok"}

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
    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type=file.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={file.filename}"
        }
    )
