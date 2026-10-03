from fastapi.testclient import TestClient
from unittest.mock import patch
import pytest

from app.main import app
from app import transcription

client = TestClient(app)

@pytest.fixture
def mock_transcribe_audio():
    with patch("app.main.transcribe_audio") as mock_transcribe:
        yield mock_transcribe

def test_transcribe_missing_audio():
    response = client.post("/api/memories/transcribe")
    assert response.status_code == 422  # FastAPI validation error for missing file

def test_transcribe_unsupported_audio():
    response = client.post(
        "/api/memories/transcribe",
        files={"file": ("notes.txt", b"not audio", "text/plain")}
    )
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unsupported audio format. Please upload a supported audio file."
    }

def test_transcribe_empty_audio():
    response = client.post(
        "/api/memories/transcribe",
        files={"file": ("empty.wav", b"", "audio/wav")}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Uploaded file is empty."}

def test_transcribe_successful_audio(mock_transcribe_audio):
    mock_transcribe_audio.return_value = "This is a test transcript."
    response = client.post(
        "/api/memories/transcribe",
        files={"file": ("test_audio.wav", b"fake audio data", "audio/wav")}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "transcribed", "transcript": "This is a test transcript."}
    mock_transcribe_audio.assert_called_once()

def test_transcribe_failure_returns_useful_error(mock_transcribe_audio):
    mock_transcribe_audio.side_effect = RuntimeError("decoder failed")
    response = client.post(
        "/api/memories/transcribe",
        files={"file": ("test_audio.wav", b"fake audio data", "audio/wav")}
    )
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Transcription failed. Check that the audio file is valid and try again."
    }

def test_whisper_model_uses_configured_model_and_cpu_int8(monkeypatch):
    model = object()
    monkeypatch.setattr(transcription, "_model", None)
    monkeypatch.setattr(transcription, "WHISPER_MODEL", "small")
    with patch("app.transcription.WhisperModel", return_value=model) as model_factory:
        assert transcription.get_whisper_model() is model
        model_factory.assert_called_once_with("small", device="cpu", compute_type="int8")
    monkeypatch.setattr(transcription, "_model", None)