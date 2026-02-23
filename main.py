from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io, zipfile
from PIL import Image, ImageEnhance, ImageFilter

app = FastAPI(title="Amazon Image Optimizer")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- HELPERS ----------------
def auto_white_bg(img):
    img = img.convert("RGBA")
    white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white_bg.paste(img, (0, 0), img)
    return white_bg.convert("RGB")

def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Sharpness(img).enhance(1.10)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

def smart_crop(img):
    bbox = img.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

# ---------------- CORE PIPELINE ----------------
def process_pipeline(img_bytes):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    img = smart_crop(img)
    img = auto_white_bg(img)
    img = enhance(img)

    CANVAS = 2000
    target = int(CANVAS * 0.85)

    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    background = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))

    x = (CANVAS - img.width) // 2
    y = (CANVAS - img.height) // 2

    background.paste(img, (x, y))

    out = io.BytesIO()
    background.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        final = process_pipeline(image_bytes)

        return StreamingResponse(
            io.BytesIO(final),
            media_type="image/jpeg"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for f in files:
            img_bytes = await f.read()
            final = process_pipeline(img_bytes)
            zipf.writestr(f"amazon_{f.filename}", final)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip"
    )

@app.get("/")
def root():
    return {"status": "ok"}
