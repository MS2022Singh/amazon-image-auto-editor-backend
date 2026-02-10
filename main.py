from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io, zipfile
from PIL import Image, ImageEnhance, ImageFilter

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- SMART CROP ----------
def smart_crop(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

# ---------- WHITE BALANCE ----------
def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.07)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    return img

# ---------- REFLECTION REDUCER ----------
def remove_reflection(img):
    return img.filter(ImageFilter.SMOOTH_MORE)

# ---------- AMAZON FRAME ----------
def amazon_frame(img, bg_color="white"):
    CANVAS = 2000
    img = smart_crop(img)

    w,h = img.size
    scale = min((CANVAS*0.9)/w, (CANVAS*0.9)/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg_map = {
        "white": (255,255,255),
        "offwhite": (245,245,245),
        "grey": (240,240,240)
    }

    bg = Image.new("RGBA",(CANVAS,CANVAS),(*bg_map.get(bg_color,(255,255,255)),255))
    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    bg.paste(img,(x,y),img)

    return bg.convert("RGB")

# ---------- PROCESS ----------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white")
):
    img = Image.open(io.BytesIO(await file.read())).convert("RGBA")

    img = remove_reflection(img)
    img = auto_white_balance(img)
    img = amazon_frame(img, bg_color)

    out = io.BytesIO()
    img.save(out,"JPEG",quality=95)

    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="image/jpeg")

# ---------- PREVIEW ----------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white")
):
    img = Image.open(io.BytesIO(await file.read())).convert("RGBA")
    img = remove_reflection(img)
    img = auto_white_balance(img)
    img = amazon_frame(img, bg_color)

    out = io.BytesIO()
    img.save(out,"JPEG",quality=90)

    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="image/jpeg")
