from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="Amazon Image Auto Editor")

# CORS (frontend ke liye future ready)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# COMMON IMAGE PROCESS FUNCTION
# -----------------------------
def process_image_logic(img: Image.Image) -> io.BytesIO:
    """
    Yahin future me:
    - white background
    - resize 2000x2000
    - centering
    add hoga
    """
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf


# -----------------------------
# ROOT CHECK
# -----------------------------
@app.get("/")
def root():
    return {"status": "Backend is running"}


# -----------------------------
# PREVIEW ENDPOINT
# -----------------------------
@app.post("/process/preview")
async def preview_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    buf = process_image_logic(img)

    return StreamingResponse(
        buf,
        media_type="image/jpeg"
    )


# -----------------------------
# DOWNLOAD ENDPOINT
# -----------------------------
@app.post("/process/download")
async def download_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    buf = process_image_logic(img)

    headers = {
        "Content-Disposition": "attachment; filename=amazon_ready.jpg"
    }

    return StreamingResponse(
        buf,
        media_type="image/jpeg",
        headers=headers
    )



