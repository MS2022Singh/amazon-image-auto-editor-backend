const API = "https://amazon-image-auto-editor-backend-production.up.railway.app";
const fileInput = document.getElementById("fileInput");

fileInput.addEventListener("change", previewImage);

function getBg(){
    return document.getElementById("bgSelect").value;
}

async function previewImage(){

    const file = fileInput.files[0];
    if(!file) return;

    const form = new FormData();
    form.append("file", file);
    form.append("bg_color", getBg());

    const res = await fetch(`${API}/process/preview`,{
        method:"POST",
        body:form
    });

    const blob = await res.blob();
    document.getElementById("previewImg").src = URL.createObjectURL(blob);
}

async function downloadImage(){

    const file = fileInput.files[0];
    if(!file) return;

    const form = new FormData();
    form.append("file", file);
    form.append("bg_color", getBg());

    const res = await fetch(`${API}/process`,{
        method:"POST",
        body:form
    });

    const blob = await res.blob();

    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "amazon_image.jpg";
    a.click();
}
