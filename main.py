from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageEnhance, ImageFilter
import io, zipfile

app = FastAPI(title="Amazon Image Auto Editor PRO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- REFLECTION REMOVER ----------------
def remove_reflection(img):
    return img.filter(ImageFilter.MedianFilter(size=3))

# ---------------- AUTO WHITE BALANCE ----------------
def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.06)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    return img

# ---------------- AMAZON SMART FRAME ----------------
def amazon_frame(img, bg_color="white", add_shadow=0):

    CANVAS = 2000
    fill = 0.9

    w,h = img.size
    scale = min((CANVAS*fill)/w,(CANVAS*fill)/h)
    img = img.resize((int(w*scale),int(h*scale)))

    colors = {
        "white":(255,255,255),
        "offwhite":(245,245,245),
        "grey":(240,240,240),
        "black":(0,0,0)
    }

    bg = Image.new("RGBA",(CANVAS,CANVAS),(*colors.get(bg_color,(255,255,255)),255))

    x = (CANVAS-img.width)//2
    y = (CANVAS-img.height)//2
    bg.paste(img,(x,y),img)

    if add_shadow==1:
        shadow = bg.filter(ImageFilter.GaussianBlur(8))
        bg = Image.blend(shadow,bg,0.85)

    return bg.convert("RGB")

# ---------------- MASTER PROCESS PIPELINE ----------------
def process_pipeline(image_bytes, bg_color="white", add_shadow=0):

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    img = remove_reflection(img)
    img = auto_white_balance(img)
    final = amazon_frame(img,bg_color,add_shadow)

    buf = io.BytesIO()
    final.save(buf,"JPEG",quality=95)

    return buf.getvalue()

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status":"ok"}

# ---------------- PROCESS ----------------
@app.post("/process")
async def process(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    result = process_pipeline(await file.read(),bg_color,add_shadow)

    return StreamingResponse(
        io.BytesIO(result),
        media_type="image/jpeg"
    )

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(
    file: UploadFile = File(...),
    bg_color: str = Form("white"),
    add_shadow: int = Form(0)
):
    result = process_pipeline(await file.read(),bg_color,add_shadow)

    return StreamingResponse(io.BytesIO(result),media_type="image/jpeg")

# ---------------- VALIDATE ----------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    w,h = img.size
    return {"square":w==h,"resolution_ok":w>=1600}

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            result = process_pipeline(await f.read())
            zipf.writestr(f"amazon_{f.filename}",result)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )
