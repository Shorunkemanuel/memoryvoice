import os

from faster_whisper import WhisperModel

_model = None
WHISPER_MODEL = os.getenv("WHISPER_MODEL") or "tiny"


def get_whisper_model():
    global _model
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def transcribe_audio(audio_file_path: str) -> str:
    model = get_whisper_model()
    segments, _ = model.transcribe(audio_file_path, beam_size=5)
    return "".join(segment.text for segment in segments).strip()
