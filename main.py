from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import PIL import Image
import io


app = FastAPI()

# CORS (frontend se call ke liye)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "Backend is running"}

@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # White background
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")

    # Amazon canvas
    canvas_size = 2000
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    img.thumbnail((1600, 1600))

    x = (canvas_size - img.width) // 2
    y = (canvas_size - img.height) // 2

    canvas.paste(img, (x, y))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "attachment; filename=amazon_ready.jpg"
        }
    )


# Render needs this
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


