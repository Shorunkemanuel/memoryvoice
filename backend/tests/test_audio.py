import io
import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_audio_success():
    audio_data = b"RIFF....WAVEfmt ..."
    response = client.post(
        "/api/memories/audio",
        files={"file": ("test.webm", io.BytesIO(audio_data), "audio/webm")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert "filename" in data
    
    # Clean up uploaded test file
    filename = data["filename"]
    filepath = os.path.join("backend", "data", "uploads", filename)
    if os.path.exists(filepath):
        os.remove(filepath)

def test_upload_audio_missing_file():
    response = client.post("/api/memories/audio")
    assert response.status_code == 400
    assert "detail" in response.json()

def test_upload_audio_empty_file():
    response = client.post(
        "/api/memories/audio",
        files={"file": ("test.webm", io.BytesIO(b""), "audio/webm")}
    )
    assert response.status_code == 400
