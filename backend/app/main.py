import os
import pathlib
import uuid
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, status

app = FastAPI(title="MemoryVoice Backend")

UPLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/memories/audio")
async def upload_audio(file: Optional[UploadFile] = File(None)):
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file provided."
        )

    ext = ".webm"
    if file.filename and "." in file.filename:
        orig_ext = pathlib.Path(file.filename).suffix.lower()
        if orig_ext in [".webm", ".mp4", ".ogg", ".wav", ".m4a", ".mp3", ".3gp", ".flac"]:
            ext = orig_ext

    safe_filename = f"{uuid.uuid4()}{ext}"
    file_path = UPLOAD_DIR / safe_filename

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file: {str(e)}"
        )

    return {
        "status": "received",
        "filename": safe_filename
    }
