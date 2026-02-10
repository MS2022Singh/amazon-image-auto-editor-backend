from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageEnhance, ImageFilter
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- IMAGE PROCESS ----------
def process_image_pipeline(img, bg_color="white", add_shadow=0):

    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Brightness(img).enhance(1.05)

    CANVAS = 2000
    w, h = img.size
    scale = min((CANVAS*0.9)/w, (CANVAS*0.9)/h)
    img = img.resize((int(w*scale), int(h*scale)))

    colors = {
        "white": (255,255,255),
        "offwhite": (245,245,245),
        "grey": (240,240,240),
        "black": (0,0,0),
    }

    bg = Image.new("RGBA", (CANVAS,CANVAS), (*colors.get(bg_color,(255,255,255)),255))

    x = (CANVAS - img.width)//2
    y = (CANVAS - img.height)//2
    bg.paste(img,(x,y),img)

    if add_shadow == 1:
        shadow = bg.filter(ImageFilter.GaussianBlur(8))
        bg = Image.blend(shadow, bg, 0.85)

    return bg.convert("RGB")

# ---------- PROCESS ----------
@app.post("/process")
async def process(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    img = Image.open(io.BytesIO(await file.read())).convert("RGBA")

    final = process_image_pipeline(img, bg_color, add_shadow)

    buf = io.BytesIO()
    final.save(buf, "JPEG", quality=95)

    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type="image/jpeg")

# ---------- PREVIEW ----------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    img = Image.open(io.BytesIO(await file.read())).convert("RGBA")

    final = process_image_pipeline(img, bg_color, add_shadow)

    buf = io.BytesIO()
    final.save(buf, "JPEG", quality=90)

    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type="image/jpeg")
