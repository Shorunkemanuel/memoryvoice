import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError


class MemoryExtractionError(RuntimeError):
    pass


class MissingTranscriptError(MemoryExtractionError):
    pass


class BackboardConfigurationError(MemoryExtractionError):
    pass


class BackboardAPIError(MemoryExtractionError):
    pass


class MalformedModelResponseError(MemoryExtractionError):
    pass


class StructuredMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: StrictStr
    people: list[StrictStr]
    places: list[StrictStr]
    dates: list[StrictStr]
    events: list[StrictStr]
    details: list[StrictStr]


def _coerce_memory_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MalformedModelResponseError("The model returned malformed JSON output.") from exc

    if not isinstance(payload, dict):
        raise MalformedModelResponseError("The model response was not a JSON object.")

    try:
        return StructuredMemory.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise MalformedModelResponseError("The model returned a malformed memory object.") from exc


def _backboard_api_url() -> str:
    return (os.getenv("BACKBOARD_API_URL") or "https://app.backboard.io/api").rstrip("/")


def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise BackboardConfigurationError(f"{name} is not configured.")
    return value.strip()


def _backboard_headers() -> dict[str, str]:
    api_key = _required_setting("BACKBOARD_API_KEY")
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }


def extract_memory(transcript: str) -> dict[str, Any]:
    if transcript is None or not str(transcript).strip():
        raise MissingTranscriptError("Transcript is required.")

    provider = _required_setting("BACKBOARD_LLM_PROVIDER")
    model = _required_setting("BACKBOARD_MODEL")
    assistant_id = _required_setting("BACKBOARD_ASSISTANT_ID")
    headers = _backboard_headers()

    instruction = (
        "Extract a structured memory strictly from the transcript. "
        "Only include facts that are explicitly stated in the transcript. "
        "Do not infer emotions, relationships, circumstances, dates, events, or details. "
        "Do not generate narrative interpretation. "
        "If information is missing, use empty arrays. "
        "Return valid JSON with the exact shape: "
        "{\"title\": \"string\", \"people\": [], \"places\": [], \"dates\": [], \"events\": [], \"details\": []}."
    )

    payload = {
        "assistant_id": assistant_id,
        "content": transcript,
        "system_prompt": instruction,
        "llm_provider": provider,
        "model_name": model,
        "stream": False,
        "json_output": True,
    }

    try:
        response = httpx.post(
            f"{_backboard_api_url()}/threads/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise BackboardAPIError("Backboard extraction request failed.") from exc

    if response.status_code >= 400:
        raise BackboardAPIError(
            f"Backboard extraction failed with status {response.status_code}: {response.text}"
        )

    try:
        response_json = response.json()
    except ValueError as exc:
        raise MalformedModelResponseError("Backboard returned non-JSON output.") from exc

    if not isinstance(response_json, dict) or not isinstance(response_json.get("content"), str):
        raise MalformedModelResponseError("Backboard returned no model content.")

    return _coerce_memory_payload(response_json["content"])


def persist_memory(memory: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memory, dict):
        raise MalformedModelResponseError("Memory payload must be an object.")

    validated_memory = _coerce_memory_payload(memory)
    assistant_id = _required_setting("BACKBOARD_ASSISTANT_ID")
    headers = _backboard_headers()
    payload = {
        "content": json.dumps(validated_memory, ensure_ascii=False),
        "metadata": {
            "source": "memoryvoice",
            "type": "structured_memory",
        },
    }

    try:
        response = httpx.post(
            f"{_backboard_api_url()}/assistants/{assistant_id}/memories",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise BackboardAPIError("Backboard persistence request failed.") from exc

    if response.status_code >= 400:
        raise BackboardAPIError(
            f"Backboard persistence failed with status {response.status_code}: {response.text}"
        )

    return validated_memory


def list_memories() -> list[dict[str, Any]]:
    assistant_id = _required_setting("BACKBOARD_ASSISTANT_ID")
    headers = _backboard_headers()

    try:
        response = httpx.get(
            f"{_backboard_api_url()}/assistants/{assistant_id}/memories",
            headers=headers,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise BackboardAPIError("Backboard memory retrieval request failed.") from exc

    if response.status_code >= 400:
        raise BackboardAPIError(
            f"Backboard memory retrieval failed with status {response.status_code}: {response.text}"
        )

    try:
        response_json = response.json()
    except ValueError as exc:
        raise MalformedModelResponseError("Backboard returned non-JSON memory data.") from exc

    if not isinstance(response_json, dict) or not isinstance(response_json.get("memories"), list):
        raise MalformedModelResponseError("Backboard returned a malformed memory list.")

    memories = []
    for item in response_json["memories"]:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise MalformedModelResponseError("Backboard returned a malformed memory.")
        memories.append(_coerce_memory_payload(item["content"]))

    return memories


def answer_memory_question(question: str) -> str:
    if not question or not question.strip():
        raise ValueError("Question is required.")

    provider = _required_setting("BACKBOARD_LLM_PROVIDER")
    model = _required_setting("BACKBOARD_MODEL")
    assistant_id = _required_setting("BACKBOARD_ASSISTANT_ID")
    headers = _backboard_headers()

    instruction = (
        "Answer the user's question using only information available in the persisted memories "
        "retrieved for this assistant. Do not use outside knowledge, make inferences, or invent "
        "facts. If the saved memories do not explicitly support an answer, respond exactly: "
        "\"That information is not available in your saved memories.\""
    )
    payload = {
        "assistant_id": assistant_id,
        "content": question.strip(),
        "system_prompt": instruction,
        "llm_provider": provider,
        "model_name": model,
        "memory": "Readonly",
        "stream": False,
        "json_output": False,
    }

    try:
        response = httpx.post(
            f"{_backboard_api_url()}/threads/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise BackboardAPIError("Backboard memory question request failed.") from exc

    if response.status_code >= 400:
        raise BackboardAPIError(
            f"Backboard memory question failed with status {response.status_code}: {response.text}"
        )

    try:
        response_json = response.json()
    except ValueError as exc:
        raise MalformedModelResponseError("Backboard returned non-JSON answer data.") from exc

    answer = response_json.get("content") if isinstance(response_json, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise MalformedModelResponseError("Backboard returned no answer content.")

    return answer.strip()
