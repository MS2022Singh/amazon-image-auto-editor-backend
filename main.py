from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import requests, io, os, zipfile
from PIL import Image

app = FastAPI(title="Amazon Image Auto Editor")

REMOVEBG_API_KEY = os.getenv("REMOVEBG_API_KEY")

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok"}

# -----------------------------
# REMOVE.BG
# -----------------------------
def remove_bg(image_bytes: bytes) -> bytes:
    if not REMOVEBG_API_KEY:
        raise RuntimeError("Remove.bg API key missing")

    r = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        files={"image_file": image_bytes},
        data={"size": "auto"},
        timeout=30
    )

    if r.status_code != 200:
        raise RuntimeError(r.text)

    return r.content  # transparent PNG

# -----------------------------
# SHADOW FREE AMAZON COMPOSE
# -----------------------------
def compose_shadow_free_white(product_rgba: Image.Image, canvas=2000) -> Image.Image:
    bg = Image.new("RGBA", (canvas, canvas), (255, 255, 255, 255))

    pw, ph = product_rgba.size
    scale = min(canvas * 0.85 / pw, canvas * 0.85 / ph)
    product = product_rgba.resize(
        (int(pw * scale), int(ph * scale)), Image.LANCZOS
    )

    # HARD alpha cleanup
    r, g, b, a = product.split()
    a = a.point(lambda p: 255 if p > 200 else 0)
    product = Image.merge("RGBA", (r, g, b, a))

    x = (canvas - product.width) // 2
    y = (canvas - product.height) // 2
    bg.paste(product, (x, y), product)

    return bg.convert("RGB")

# -----------------------------
# AMAZON PIPELINE
# -----------------------------
def amazon_process(image_bytes: bytes, canvas=2000) -> bytes:
    transparent = remove_bg(image_bytes)
    product = Image.open(io.BytesIO(transparent)).convert("RGBA")
    final = compose_shadow_free_white(product, canvas)

    out = io.BytesIO()
    final.save(out, "JPEG", quality=95, subsampling=0)
    out.seek(0)
    return out.read()

# -----------------------------
# AMAZON VALIDATOR
# -----------------------------
def amazon_validator(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size

    corners = [
        img.getpixel((0, 0)),
        img.getpixel((w-1, 0)),
        img.getpixel((0, h-1)),
        img.getpixel((w-1, h-1)),
    ]

    background_white = all(
        abs(r-255) < 3 and abs(g-255) < 3 and abs(b-255) < 3
        for r, g, b in corners
    )

    return {
        "square": w == h,
        "resolution_ok": w >= 1600,
        "background_white": background_white,
        "amazon_safe": w == h and w >= 1600 and background_white
    }

# -----------------------------
# PREVIEW
# -----------------------------
@app.post("/process/preview")
async def preview(file: UploadFile = File(...)):
    image_bytes = await file.read()
    preview = amazon_process(image_bytes, canvas=1200)

    return StreamingResponse(io.BytesIO(preview), media_type="image/jpeg")

# -----------------------------
# FINAL DOWNLOAD
# -----------------------------
@app.post("/process")
async def process(file: UploadFile = File(...)):
    image_bytes = await file.read()
    final = amazon_process(image_bytes)

    return StreamingResponse(
        io.BytesIO(final),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"attachment; filename=amazon_{file.filename}"
        }
    )

# -----------------------------
# VALIDATE
# -----------------------------
@app.post("/process/validate")
async def validate(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return amazon_validator(image_bytes)

# -----------------------------
# BATCH
# -----------------------------
@app.post("/process/batch")
async def batch(files: list[UploadFile] = File(...)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for file in files:
            img_bytes = await file.read()
            final = amazon_process(img_bytes)
            zipf.writestr(f"amazon_{file.filename}", final)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=amazon_images.zip"}
    )
