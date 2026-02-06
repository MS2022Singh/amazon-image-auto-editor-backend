from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests, io, os, zipfile
from PIL import Image, ImageEnhance, ImageFilter
from datetime import datetime
from openai import OpenAI

client = OpenAI()

app = FastAPI(title="Amazon Image Auto Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

# ---------- DAILY LIMIT ----------
DAILY_LIMIT = 10
usage_store = {}

def check_usage(ip):
    today = datetime.utcnow().date()

    if ip not in usage_store:
        usage_store[ip] = {"date": today, "count": 0}

    record = usage_store[ip]

    if record["date"] != today:
        record["date"] = today
        record["count"] = 0

    if record["count"] >= DAILY_LIMIT:
        return False

    record["count"] += 1
    return True

# ---------- ROOT ----------
@app.get("/")
def root():
    return {"status": "ok"}

# ---------- REMOVE BG ----------
def remove_bg(image_bytes: bytes) -> bytes:
    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
    )
    return r.content

# ---------- IMAGE HELPERS ----------
def smart_crop_rgba(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

def studio_lighting_correction(img):
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.05)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    img = img.filter(ImageFilter.SMOOTH)
    return img

def amazon_ready_image(img_bytes: bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img = smart_crop_rgba(img)

    CANVAS = 2000
    target = int(CANVAS * 0.90)

    w, h = img.size
    scale = min(target / w, target / h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    background = Image.new("RGBA", (CANVAS, CANVAS), (255,255,255,255))
    x = (CANVAS - img.width)//2
    y = (CANVAS - img.height)//2
    background.paste(img,(x,y),img)

    background = studio_lighting_correction(background.convert("RGB"))

    out = io.BytesIO()
    background.save(out,"JPEG",quality=95)
    return out.getvalue()

# ---------- PROCESS ----------
@app.post("/process")
async def process_image(request: Request, file: UploadFile = File(...)):
    user_ip = request.client.host

    if not check_usage(user_ip):
        return {"error": "Daily free limit reached"}

    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)

    return StreamingResponse(
        io.BytesIO(final),
        media_type="image/jpeg",
        headers={"Content-Disposition": f"attachment; filename=amazon_{file.filename}"}
    )

# ---------- PREVIEW ----------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    transparent = remove_bg(image_bytes)
    final = amazon_ready_image(transparent)
    return StreamingResponse(io.BytesIO(final), media_type="image/jpeg")

# ---------- BATCH ----------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer,"w") as zipf:
        for f in files:
            img_bytes = await f.read()
            transparent = remove_bg(img_bytes)
            final = amazon_ready_image(transparent)
            zipf.writestr(f"amazon_{f.filename}", final)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition":"attachment; filename=amazon_images.zip"}
    )

# ---------- AI LISTING TEXT ----------
def generate_listing_text(product_name: str):
    prompt = f"Create an optimized Amazon listing for: {product_name}"

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7
    )

    return resp.choices[0].message.content

@app.post("/process/listing-text")
async def listing_text(product_name: str = Form(...)):
    text = generate_listing_text(product_name)
    return {"listing": text}
