from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import zipfile
from PIL import Image, ImageEnhance, ImageFilter
from rembg import remove, new_session

app = FastAPI(title="Amazon Image Auto Editor")

# ---------------- CORS (FINAL SAFE CONFIG) ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- REMBG SESSION CACHE ----------------
REM_BG_SESSION = None

@app.on_event("startup")
def preload_model():
    global REM_BG_SESSION
    REM_BG_SESSION = new_session()

def get_rembg_session():
    global REM_BG_SESSION
    if REM_BG_SESSION is None:
        REM_BG_SESSION = new_session()
    return REM_BG_SESSION

# ---------------- INTERNAL WHITE BG FALLBACK ----------------
def internal_white_bg(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img)
    out = io.BytesIO()
    bg.save(out, "JPEG", quality=95)
    return out.getvalue()

# ---------------- REMOVE BG SAFE ----------------
def remove_bg_safe(image_bytes):
    try:
        session = get_rembg_session()
        output = remove(image_bytes, session=session)
        if not output or len(output) < 1000:
            return internal_white_bg(image_bytes)
        return output
    except Exception:
        return internal_white_bg(image_bytes)

# ---------------- IMAGE HELPERS ----------------
def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

def resolve_background(bg_color):
    presets = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "lightgrey": (240, 240, 240),
    }
    return presets.get(bg_color, (255, 255, 255))

# ---------------- CORE PIPELINE ----------------
def process_pipeline(img_bytes, bg_color="white", add_shadow=0):

    transparent = remove_bg_safe(img_bytes)
    img = Image.open(io.BytesIO(transparent)).convert("RGBA")

    CANVAS = 2000
    TARGET = int(CANVAS * 0.9)

    w, h = img.size
    if w == 0 or h == 0:
        return internal_white_bg(img_bytes)

    scale = min(TARGET / w, TARGET / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA", (CANVAS, CANVAS), (*bg_rgb, 255))

    x = (CANVAS - img.width) // 2
    y = (CANVAS - img.height) // 2
    background.paste(img, (x, y), img)

    if add_shadow == 1:
        shadow = background.filter(ImageFilter.GaussianBlur(35))
        background = Image.blend(background, shadow, 0.15)

    final = enhance(background.convert("RGB"))

    out = io.BytesIO()
    final.save(out, "JPEG", quality=95, optimize=True)
    return out.getvalue()

# ---------------- SIZE LIMIT ----------------
def compress_to_limit(img_bytes, max_kb=9000):
    img = Image.open(io.BytesIO(img_bytes))
    q = 95
    while True:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True)
        if len(buf.getvalue()) / 1024 <= max_kb or q <= 70:
            return buf.getvalue()
        q -= 2

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0),
):
    image_bytes = await file.read()
    final = process_pipeline(image_bytes, bg_color, add_shadow)
    final = compress_to_limit(final)
    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def process_preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0),
):
    try:
        image_bytes = await file.read()
        preview = process_pipeline(image_bytes, bg_color, add_shadow)
        return StreamingResponse(io.BytesIO(preview), media_type="image/jpeg")
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
    return StreamingResponse(zip_buffer, media_type="application/zip")

@app.get("/")
def root():
    return {"status": "ok"}
