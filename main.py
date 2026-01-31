from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import numpy as np
import cv2
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

    # Read image with OpenCV
    np_img = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Create mask (simple & safe)
    _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    product = cv2.bitwise_and(img, img, mask=mask)

    # Amazon canvas
    canvas_size = 2000
    canvas = np.ones((canvas_size, canvas_size, 3), dtype=np.uint8) * 255

    h, w = product.shape[:2]
    scale = min(1600/w, 1600/h)
    new_w, new_h = int(w*scale), int(h*scale)

    product_resized = cv2.resize(product, (new_w, new_h))

    x = (canvas_size - new_w) // 2
    y = (canvas_size - new_h) // 2

    canvas[y:y+new_h, x:x+new_w] = product_resized

    _, jpg = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return StreamingResponse(
        io.BytesIO(jpg.tobytes()),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "attachment; filename=amazon_ready.jpg"
        }
    )


# Render needs this
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

