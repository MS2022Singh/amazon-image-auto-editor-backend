from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import Response
from PIL import Image
from rembg import remove
session = none
from io import BytesIO
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
def make_amazon_white_bg(image_bytes: bytes) -> Image.Image:
    global session
    if session is None:
        from rembg import new_session
        session = new_session("u2netp")
try:
    # Remove background
    cutout = remove(image_bytes, session=session)

    # Open as RGBA
    img = Image.open(BytesIO(cutout)).convert("RGBA")

    # Create pure white background
    white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))

    # Composite product on white bg
    final_img = Image.alpha_composite(white_bg, img)

    return final_img.convert("RGB")

except Exception as e:
    raise RuntimeError(f"Image Processing failed: {str(e)}")


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
    if len(image_bytes)>10*1024*1024:
        return Response("File too large",status_code=413)

    final_img = make_amazon_white_bg(image_bytes)

    buf = BytesIO()
    final_img.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/jpeg",
                            headers={"Cache-Control":"no-store"})


# -----------------------------
# DOWNLOAD ENDPOINT
# -----------------------------
@app.post("/process/download")
async def download_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    final_img = make_amazon_white_bg(image_bytes)

    buf = BytesIO()
    final_img.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "attachment; filename=amazon_ready.jpg"
        }
    )








