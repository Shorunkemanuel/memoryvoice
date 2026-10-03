import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.memory import (
    BackboardAPIError,
    BackboardConfigurationError,
    MalformedModelResponseError,
    MissingTranscriptError,
    extract_memory,
    persist_memory,
)

client = TestClient(app)


def test_create_memory_missing_transcript():
    response = client.post("/api/memories", json={})
    assert response.status_code == 400
    assert response.json() == {"detail": "Transcript is required."}


def test_create_memory_empty_transcript():
    response = client.post("/api/memories", json={"transcript": "   "})
    assert response.status_code == 400
    assert response.json() == {"detail": "Transcript is required."}


def test_extract_memory_uses_backboard_message_contract(monkeypatch):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("BACKBOARD_MODEL", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")
    monkeypatch.setenv("BACKBOARD_API_URL", "https://example.test/api")

    expected_memory = {
        "title": "Visit with Grandma",
        "people": ["Grandmother", "Samuel"],
        "places": ["Ibadan"],
        "dates": ["Last Sunday", "1970s"],
        "events": ["visited grandmother", "grandmother was a teacher"],
        "details": [
            "Grandmother shared stories about her teaching years",
            "They discussed grandfather Samuel",
        ],
    }
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": json.dumps(expected_memory)}

    with patch("app.memory.httpx.post", return_value=mock_response) as post_mock:
        result = extract_memory(
            "Last Sunday I visited my grandmother in Ibadan. She told me stories "
            "about when she was a teacher in the 1970s."
        )

    assert result == expected_memory
    post_mock.assert_called_once()
    args, kwargs = post_mock.call_args
    assert args[0] == "https://example.test/api/threads/messages"
    assert kwargs["headers"]["X-API-Key"] == "test-key"
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["json"]["assistant_id"] == "assistant-123"
    assert "Last Sunday I visited my grandmother" in kwargs["json"]["content"]
    assert kwargs["json"]["system_prompt"]
    assert kwargs["json"]["llm_provider"] == "openrouter"
    assert kwargs["json"]["model_name"] == "meta-llama/llama-3.1-8b-instruct"
    assert kwargs["json"]["stream"] is False
    assert kwargs["json"]["json_output"] is True
    assert kwargs["json"] == {
        "assistant_id": "assistant-123",
        "content": (
            "Last Sunday I visited my grandmother in Ibadan. She told me stories "
            "about when she was a teacher in the 1970s."
        ),
        "system_prompt": kwargs["json"]["system_prompt"],
        "llm_provider": "openrouter",
        "model_name": "meta-llama/llama-3.1-8b-instruct",
        "stream": False,
        "json_output": True,
    }
    assert (
        "Only include facts that are explicitly stated in the transcript."
        in kwargs["json"]["system_prompt"]
    )
    assert "Do not infer emotions, relationships, circumstances, dates, events, or details." in kwargs[
        "json"
    ]["system_prompt"]
    assert "If information is missing, use empty arrays." in kwargs["json"]["system_prompt"]
    assert "Do not generate narrative interpretation." in kwargs["json"]["system_prompt"]
    assert not {"provider", "model", "messages", "response_format"} & kwargs["json"].keys()


@pytest.mark.parametrize(
    "missing_setting",
    [
        "BACKBOARD_API_KEY",
        "BACKBOARD_LLM_PROVIDER",
        "BACKBOARD_MODEL",
        "BACKBOARD_ASSISTANT_ID",
    ],
)
def test_extract_memory_requires_configuration(monkeypatch, missing_setting):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("BACKBOARD_MODEL", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")
    monkeypatch.delenv(missing_setting)

    with patch("app.memory.httpx.post") as post_mock:
        with pytest.raises(BackboardConfigurationError, match=f"{missing_setting} is not configured"):
            extract_memory("A transcript.")
    post_mock.assert_not_called()


def test_extract_memory_rejects_malformed_model_content(monkeypatch):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("BACKBOARD_MODEL", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": '{"title":'}
    with patch("app.memory.httpx.post", return_value=mock_response):
        with pytest.raises(MalformedModelResponseError):
            extract_memory("A transcript.")


def test_extract_memory_handles_backboard_http_failure(monkeypatch):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("BACKBOARD_MODEL", "meta-llama/llama-3.1-8b-instruct")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")

    mock_response = Mock()
    mock_response.status_code = 503
    mock_response.text = "Unavailable"
    with patch("app.memory.httpx.post", return_value=mock_response):
        with pytest.raises(BackboardAPIError, match="status 503"):
            extract_memory("A transcript.")


def test_create_memory_malformed_model_response(monkeypatch):
    monkeypatch.setattr("app.main.extract_memory", Mock(side_effect=MalformedModelResponseError("bad response")))
    response = client.post("/api/memories", json={"transcript": "This is a transcript."})
    assert response.status_code == 500
    assert response.json() == {"detail": "The model returned malformed memory data."}


def test_create_memory_backboard_failure(monkeypatch):
    monkeypatch.setattr("app.main.extract_memory", Mock(side_effect=BackboardAPIError("upstream failure")))
    response = client.post("/api/memories", json={"transcript": "This is a transcript."})
    assert response.status_code == 502
    assert response.json() == {"detail": "Backboard memory service failed. Please try again."}


def test_create_memory_success(monkeypatch):
    payload = {
        "title": "Visit with Grandma",
        "people": ["Grandmother", "Samuel"],
        "places": ["Ibadan"],
        "dates": ["Last Sunday", "1970s"],
        "events": ["visited grandmother", "grandmother was a teacher"],
        "details": [
            "Grandmother shared stories about her teaching years",
            "They discussed grandfather Samuel",
        ],
    }
    monkeypatch.setattr("app.main.extract_memory", Mock(return_value=payload))
    monkeypatch.setattr("app.main.persist_memory", Mock(return_value=payload))

    response = client.post(
        "/api/memories",
        json={"transcript": "Last Sunday I visited my grandmother in Ibadan."},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "created", "memory": payload}


def test_persist_memory_uses_backboard_memory_contract(monkeypatch):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")
    monkeypatch.setenv("BACKBOARD_API_URL", "https://example.test/api")
    memory = {
        "title": "Visit with Grandma",
        "people": ["Grandmother", "Samuel"],
        "places": ["Ibadan"],
        "dates": ["Last Sunday"],
        "events": ["visited grandmother"],
        "details": ["They discussed grandfather Samuel"],
    }

    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"memory_id": "memory-123"}

    with patch("app.memory.httpx.post", return_value=mock_response) as post_mock:
        result = persist_memory(memory)

    assert result == memory
    post_mock.assert_called_once()
    args, kwargs = post_mock.call_args
    assert args[0] == "https://example.test/api/assistants/assistant-123/memories"
    assert kwargs["headers"]["X-API-Key"] == "test-key"
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["json"] == {
        "content": json.dumps(memory, ensure_ascii=False),
        "metadata": {"source": "memoryvoice", "type": "structured_memory"},
    }
    assert json.loads(kwargs["json"]["content"]) == memory
    assert "assistant_id" not in kwargs["json"]
    mock_response.json.assert_not_called()


def test_extract_memory_missing_transcript_raises():
    with pytest.raises(MissingTranscriptError):
        extract_memory("   ")
