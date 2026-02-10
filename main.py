from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io, zipfile
from PIL import Image, ImageEnhance, ImageFilter

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- SMART CROP ----------------
def smart_crop_rgba(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

# ---------------- WHITE BALANCE ----------------
def auto_white_balance(img):
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Brightness(img).enhance(1.03)
    return img

# ---------------- REFLECTION REMOVER ----------------
def remove_reflection(img):
    return img.filter(ImageFilter.SMOOTH_MORE)

# ---------------- AMAZON FRAME ----------------
def amazon_frame(img, canvas=2000):
    img = smart_crop_rgba(img)

    w, h = img.size
    scale = min((canvas*0.9)/w, (canvas*0.9)/h)
    img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    bg = Image.new("RGBA",(canvas,canvas),(255,255,255,255))
    x = (canvas-img.width)//2
    y = (canvas-img.height)//2
    bg.paste(img,(x,y),img)

    return bg.convert("RGB")

# ---------------- PROCESS ----------------
@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    img = remove_reflection(img)
    img = auto_white_balance(img)
    img = amazon_frame(img)

    out = io.BytesIO()
    img.save(out,"JPEG",quality=95)

    return StreamingResponse(
        io.BytesIO(out.getvalue()),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=amazon_{file.filename}"}
    )

# ---------------- PREVIEW ----------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    img = remove_reflection(img)
    img = auto_white_balance(img)
    img = amazon_frame(img)

    out = io.BytesIO()
    img.save(out,"JPEG",quality=90)

    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="image/jpeg")

# ---------------- VALIDATE ----------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    w,h = img.size
    return {"square": w==h, "resolution_ok": w>=1600}

# ---------------- BATCH ----------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            img = amazon_frame(img)
            buf = io.BytesIO()
            img.save(buf,"JPEG")
            zipf.writestr(f"amazon_{f.filename}", buf.getvalue())

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip")

# ---------------- BULK KEYWORD MINER ----------------
@app.post("/process/keyword-miner")
async def keywords(product_name: str = Form(...)):
    base = product_name.lower()
    kw = [
        base,
        f"{base} for women",
        f"premium {base}",
        f"{base} gift",
        f"best {base} online"
    ]
    return {"keywords": ", ".join(kw)}
