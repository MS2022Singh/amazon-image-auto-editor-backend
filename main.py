from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os
from PIL import Image, ImageEnhance, ImageFilter

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
    return {"status": "server running"}


# ---------- SAFE BG REMOVE ----------
def remove_bg_safe(image_bytes):

    if not REMOVEBG_API_KEY:
        return image_bytes

    try:
        r = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            headers={"X-Api-Key": REMOVEBG_API_KEY},
            files={"image_file": image_bytes},
            data={"size": "auto"},
            timeout=20
        )

        if r.status_code == 200:
            return r.content
        return image_bytes

    except:
        return image_bytes


# ---------- IMAGE PIPELINE ----------
def process_pipeline(img_bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    # reflection smooth
    img = img.filter(ImageFilter.SMOOTH_MORE)

    CANVAS = 2000
    target = int(CANVAS * 0.9)

    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # background resolve
    if bg_color == "black":
        bg = (0, 0, 0, 255)
    else:
        bg = (255, 255, 255, 255)

    background = Image.new("RGBA", (CANVAS, CANVAS), bg)

    x = (CANVAS - img.width) // 2
    y = (CANVAS - img.height) // 2
    background.paste(img, (x, y), img)

    # shadow
    if add_shadow == 1:
        shadow = background.point(lambda p: p * 0.25)
        background = Image.blend(background, shadow, 0.15)

    background = background.convert("RGB")
    background = ImageEnhance.Sharpness(background).enhance(1.15)

    out = io.BytesIO()
    background.save(out, "JPEG", quality=95, optimize=True)
    return out.getvalue()


# ---------- FINAL PROCESS ----------
@app.post("/process")
async def process_image(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg_safe(image_bytes)
    final = process_pipeline(transparent, bg_color, add_shadow)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")


# ---------- PREVIEW ----------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    image_bytes = await file.read()
    transparent = remove_bg_safe(image_bytes)
    final = process_pipeline(transparent, bg_color, add_shadow)

    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")
