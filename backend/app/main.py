import logging
import pathlib
import tempfile
import uuid
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from pydantic import BaseModel

from .memory import (
    BackboardAPIError,
    BackboardConfigurationError,
    MalformedModelResponseError,
    MissingTranscriptError,
    extract_memory,
    persist_memory,
)
from .transcription import transcribe_audio

app = FastAPI(title="MemoryVoice Backend")
logger = logging.getLogger(__name__)

UPLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SUPPORTED_AUDIO_EXTENSIONS = {".webm", ".mp4", ".ogg", ".wav", ".m4a", ".mp3", ".3gp", ".flac"}


class MemoryRequest(BaseModel):
    transcript: Optional[str] = None


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/memories")
async def create_memory(memory_request: MemoryRequest):
    transcript = (memory_request.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcript is required.")

    try:
        memory = extract_memory(transcript)
        persisted_memory = persist_memory(memory)
    except MissingTranscriptError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BackboardConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except BackboardAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backboard memory service failed. Please try again.",
        ) from exc
    except MalformedModelResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The model returned malformed memory data.",
        ) from exc

    return {"status": "created", "memory": persisted_memory}

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

@app.post("/api/memories/transcribe")
async def transcribe_memory(file: UploadFile = File(...)):
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported audio format. Please upload a supported audio file."
        )

    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, suffix=suffix, delete=False) as temp_file:
            temp_file_path = pathlib.Path(temp_file.name)
            while contents := await file.read(1024 * 1024):
                temp_file.write(contents)

        if temp_file_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )

        transcript = transcribe_audio(str(temp_file_path))
        return {
            "status": "transcribed",
            "transcript": transcript
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed. Check that the audio file is valid and try again."
        )
    finally:
        if temp_file_path is not None:
            temp_file_path.unlink(missing_ok=True)
