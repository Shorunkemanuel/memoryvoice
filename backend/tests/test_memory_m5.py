import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MEMORY = {
    "title": "Visit with Grandma",
    "people": ["Grandmother", "Samuel"],
    "places": ["Ibadan"],
    "dates": ["Last Sunday"],
    "events": ["visited grandmother"],
    "details": ["They discussed grandfather Samuel"],
}


def configure_backboard(monkeypatch):
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setenv("BACKBOARD_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("BACKBOARD_MODEL", "test-open-model")
    monkeypatch.setenv("BACKBOARD_ASSISTANT_ID", "assistant-123")
    monkeypatch.setenv("BACKBOARD_API_URL", "https://example.test/api")


def test_get_memories_uses_backboard_contract(monkeypatch):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "memories": [
            {"id": "memory-123", "content": json.dumps(MEMORY), "metadata": {"source": "memoryvoice"}}
        ],
        "total_count": 1,
    }

    with patch("app.memory.httpx.get", return_value=mock_response) as get_mock:
        response = client.get("/api/memories")

    assert response.status_code == 200
    assert response.json() == {"memories": [MEMORY]}
    get_mock.assert_called_once_with(
        "https://example.test/api/assistants/assistant-123/memories",
        headers={"X-API-Key": "test-key", "Content-Type": "application/json"},
        timeout=30,
    )
    assert "BACKBOARD_API_KEY" not in response.text


def test_get_memories_returns_empty_list(monkeypatch):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"memories": [], "total_count": 0}

    with patch("app.memory.httpx.get", return_value=mock_response):
        response = client.get("/api/memories")

    assert response.status_code == 200
    assert response.json() == {"memories": []}


def test_get_memories_handles_backboard_failure(monkeypatch):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("app.memory.httpx.get", return_value=mock_response):
        response = client.get("/api/memories")

    assert response.status_code == 502
    assert response.json() == {"detail": "Backboard memory service failed. Please try again."}


def test_get_memories_requires_configuration(monkeypatch):
    configure_backboard(monkeypatch)
    monkeypatch.delenv("BACKBOARD_API_KEY")

    with patch("app.memory.httpx.get") as get_mock:
        response = client.get("/api/memories")

    assert response.status_code == 500
    assert response.json() == {"detail": "BACKBOARD_API_KEY is not configured."}
    get_mock.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": []},
        {"memories": [{"content": "not-json"}]},
        {"memories": [{"content": json.dumps({"title": "missing arrays"})}]},
    ],
)
def test_get_memories_handles_malformed_backboard_response(monkeypatch, payload):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload

    with patch("app.memory.httpx.get", return_value=mock_response):
        response = client.get("/api/memories")

    assert response.status_code == 502
    assert response.json() == {"detail": "Backboard returned malformed memory data."}


def test_ask_memories_uses_configured_readonly_message_contract(monkeypatch):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "You visited your grandmother in Ibadan."}

    with patch("app.memory.httpx.post", return_value=mock_response) as post_mock:
        response = client.post(
            "/api/memories/ask",
            json={"question": "  What did I tell you about my grandmother?  "},
        )

    assert response.status_code == 200
    assert response.json() == {"answer": "You visited your grandmother in Ibadan."}
    post_mock.assert_called_once()
    args, kwargs = post_mock.call_args
    assert args[0] == "https://example.test/api/threads/messages"
    assert kwargs["headers"] == {"X-API-Key": "test-key", "Content-Type": "application/json"}
    assert kwargs["json"]["assistant_id"] == "assistant-123"
    assert kwargs["json"]["content"] == "What did I tell you about my grandmother?"
    assert kwargs["json"]["llm_provider"] == "openrouter"
    assert kwargs["json"]["model_name"] == "test-open-model"
    assert kwargs["json"]["memory"] == "Readonly"
    assert kwargs["json"]["stream"] is False
    assert kwargs["json"]["json_output"] is False
    assert "only information available in the persisted memories" in kwargs["json"]["system_prompt"]
    assert "Do not use outside knowledge" in kwargs["json"]["system_prompt"]
    assert "not available in your saved memories" in kwargs["json"]["system_prompt"]
    assert "Authorization" not in kwargs["headers"]


def test_ask_memories_rejects_empty_question():
    response = client.post("/api/memories/ask", json={"question": "   "})
    assert response.status_code == 400
    assert response.json() == {"detail": "Question is required."}


def test_ask_memories_handles_backboard_failure(monkeypatch):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 503
    mock_response.text = "Unavailable"

    with patch("app.memory.httpx.post", return_value=mock_response):
        response = client.post("/api/memories/ask", json={"question": "What happened?"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Backboard memory service failed. Please try again."}


def test_ask_memories_requires_configuration(monkeypatch):
    configure_backboard(monkeypatch)
    monkeypatch.delenv("BACKBOARD_MODEL")

    with patch("app.memory.httpx.post") as post_mock:
        response = client.post("/api/memories/ask", json={"question": "What happened?"})

    assert response.status_code == 500
    assert response.json() == {"detail": "BACKBOARD_MODEL is not configured."}
    post_mock.assert_not_called()


@pytest.mark.parametrize("payload", [{"unexpected": "answer"}, {"content": ""}, {"content": None}])
def test_ask_memories_handles_malformed_backboard_response(monkeypatch, payload):
    configure_backboard(monkeypatch)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload

    with patch("app.memory.httpx.post", return_value=mock_response):
        response = client.post("/api/memories/ask", json={"question": "What happened?"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Backboard returned a malformed answer."}
