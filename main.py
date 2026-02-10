from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

@app.get("/")
def root():
    return {"status": "ok"}


# -------- REMOVE BG (fallback free mode) ----------
def remove_bg(image_bytes: bytes) -> bytes:
    if REMOVEBG_API_KEY:
        try:
            r = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                headers={"X-Api-Key": REMOVEBG_API_KEY},
                files={"image_file": image_bytes},
                data={"size": "auto"},
                timeout=15
            )
            if r.status_code == 200:
                return r.content
        except:
            pass

    # fallback free unlimited mode
    return image_bytes


# -------- AUTO SQUARE ----------
def auto_square(img):
    w, h = img.size
    side = max(w, h)
    bg = Image.new("RGBA", (side, side), (255,255,255,255))
    bg.paste(img, ((side-w)//2, (side-h)//2), img)
    return bg


# -------- REFLECTION REDUCER ----------
def remove_reflection(img):
    return img.filter(ImageFilter.SMOOTH_MORE)


# -------- WHITE BALANCE ----------
def auto_white_balance(img):
    return ImageOps.autocontrast(img)


# -------- ENHANCE ----------
def enhance(img):
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Sharpness(img).enhance(1.12)
    return img


# -------- AMAZON READY ----------
def amazon_ready_image(img_bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    img = auto_square(img)
    img = remove_reflection(img)
    img = auto_white_balance(img)

    CANVAS = 2000
    target = int(CANVAS * 0.9)

    w,h = img.size
    scale = min(target/w, target/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    background = Image.new("RGBA",(CANVAS,CANVAS),(255,255,255,255))

    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    background.paste(img,(x,y),img)

    if add_shadow == 1:
        shadow = background.point(lambda p: p*0.25)
        background = Image.blend(background, shadow, 0.12)

    background = enhance(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95)
    return out.getvalue()


# -------- PROCESS ----------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent, bg_color, add_shadow)
    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")


# -------- PREVIEW ----------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent, bg_color, add_shadow)
    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")


# -------- VALIDATE ----------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    w,h = img.size
    return {"square": w==h, "resolution_ok": w>=1600}


# -------- BATCH ----------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            transparent = remove_bg(img_bytes)
            final = amazon_ready_image(transparent)
            zipf.writestr(f"amazon_{f.filename}",final)
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )


