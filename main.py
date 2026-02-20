from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io, zipfile
from PIL import Image, ImageEnhance, ImageFilter
from rembg import remove, new_session

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

# ---------------- INTERNAL WHITE BG ----------------
def internal_white_bg(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    white_bg = Image.new("RGBA", img.size, (255,255,255,255))
    gray = img.convert("L")
    mask = gray.point(lambda x: 0 if x > 235 else 255)
    white_bg.paste(img,(0,0),mask)
    out = io.BytesIO()
    white_bg.convert("RGB").save(out,"JPEG",quality=95)
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

# ---------------- HELPERS ----------------
def smart_crop_rgba(img):
    if img.mode != "RGBA":
        return img

    bbox = img.split()[-1].getbbox()
    if not bbox:
        return img

    margin = int(max(img.width, img.height) * 0.35)
    left = max(0, bbox[0]-margin)
    top = max(0, bbox[1]-margin)
    right = min(img.width, bbox[2]+margin)
    bottom = min(img.height, bbox[3]+margin)

    return img.crop((left,top,right,bottom))

def enhance(img):
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    return img

def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

def remove_reflection(img):
    return img.filter(ImageFilter.SMOOTH_MORE)

def resolve_background(bg_color):
    presets = {
        "white":(255,255,255),
        "black":(0,0,0),
        "lightgrey":(240,240,240)
    }
    return presets.get(bg_color,(255,255,255))

# ---------------- CORE PIPELINE ----------------
def process_pipeline(img_bytes, bg_color="white", add_shadow=0):

    transparent = remove_bg_safe(img_bytes)
    img = Image.open(io.BytesIO(transparent)).convert("RGBA")

    img = smart_crop_rgba(img)

    if img.width == 0 or img.height == 0:
        return internal_white_bg(img_bytes)

    img = remove_reflection(img)
    img = auto_white_balance(img)

    CANVAS = 2000
    target = int(CANVAS*0.9)

    w,h = img.size
    if w == 0 or h == 0:
        return internal_white_bg(img_bytes)

    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg_rgb = resolve_background(bg_color)
    background = Image.new("RGBA",(CANVAS,CANVAS),(*bg_rgb,255))

    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    background.paste(img,(x,y),img)

    if add_shadow == 1:
        shadow = background.filter(ImageFilter.GaussianBlur(35))
        background = Image.blend(background,shadow,0.15)

    background = enhance(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95,optimize=True)
    return out.getvalue()

# ---------------- SIZE LIMIT ----------------
def compress_to_limit(img_bytes, max_kb=9000):
    img = Image.open(io.BytesIO(img_bytes))
    q = 95
    while True:
        buf = io.BytesIO()
        img.save(buf,"JPEG",quality=q,optimize=True)
        if len(buf.getvalue())/1024 <= max_kb or q <= 70:
            return buf.getvalue()
        q -= 2

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(file: UploadFile = File(...), bg_color: str = Form("white"), add_shadow: int = Form(0)):
    image_bytes = await file.read()
    final = process_pipeline(image_bytes,bg_color,add_shadow)
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
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("RGBA")

        # -------- SAFE background removal ----------
        try:
            from rembg import remove
           session = get_rembg_session()
           img_bytes = remove(contents, session-session)
           img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        except Exception as e:
            print("Rembg skipped:", e)

        # -------- Background apply ----------
        background = Image.new("RGBA", img.size, bg_color)
        background.paste(img, (0, 0), img)

        # -------- Optional shadow ----------
        if add_shadow:
            shadow = background.filter(ImageFilter.GaussianBlur(12))
            background = Image.alpha_composite(shadow, background)

        buf = io.BytesIO()
        background.convert("RGB").save(buf, format="JPEG", quality=90)
        buf.seek(0)

        return StreamingResponse(buf, media_type="image/jpeg")

    except Exception as e:
        print("Preview error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            final = process_pipeline(img_bytes)
            zipf.writestr(f"amazon_{f.filename}",final)
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip")

@app.get("/")
def root():
    return {"status": "ok"}



