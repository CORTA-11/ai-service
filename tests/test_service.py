import asyncio
import json
import socket
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import endpoint_policy
from app.errors import AIServiceError, ErrorCode
from app.main import app
from app.models import ProcessRequest
from app.service import ContextService


def request_payload() -> dict:
    return {
        "schema_version": "1",
        "request_id": str(uuid4()),
        "operation": "chat_summary_and_actions",
        "provider": {
            "protocol": "openai_chat_completions_v1",
            "endpoint_url": "https://example.com/v1/chat/completions",
            "model": "test-model",
            "api_token": "request-secret",
        },
        "context": {
            "organization_public_id": "org-1",
            "team_public_id": "team-1",
            "reference_timestamp": "2026-09-07T12:00:00Z",
            "timezone": "UTC",
            "participants": [{"public_user_id": "user-1", "display_name": "Ada"}],
            "messages": [{
                "public_message_id": "message-1",
                "sender_public_user_id": "user-1",
                "timestamp": "2026-09-07T11:00:00Z",
                "text": "Please finish the integration tests.",
            }],
        },
        "options": {"response_language": "en", "max_action_items": 3},
    }


class FakeProvider:
    def __init__(self, result: dict):
        self.result = result
        self.request = None

    async def complete(self, request: ProcessRequest) -> str:
        self.request = request
        return json.dumps(self.result)


def valid_result() -> dict:
    return {
        "schema_version": "1",
        "summary": {
            "overview": "The team agreed to finish testing.",
            "key_points": ["Integration tests remain."],
            "decisions": [{"text": "Finish testing", "source_message_ids": ["message-1"]}],
            "open_questions": [],
        },
        "action_items": [{
            "title": "Complete integration tests",
            "description": "Finish the remaining integration tests.",
            "assignee_user_id": "user-1",
            "priority": "high",
            "due_date": None,
            "source_message_ids": ["message-1"],
            "confidence": 0.95,
        }],
    }


def test_process_validates_output_and_generates_candidate_id(monkeypatch):
    monkeypatch.setattr("app.service.validate_provider_endpoint", lambda endpoint: None)
    provider = FakeProvider(valid_result())
    request = ProcessRequest.model_validate(request_payload())

    response = asyncio.run(ContextService(provider).process(request))

    assert response.action_items[0].candidate_id
    assert isinstance(response.action_items[0].candidate_id, UUID)
    assert provider.request.provider.api_token == "request-secret"


def test_process_rejects_invented_source_message_id(monkeypatch):
    monkeypatch.setattr("app.service.validate_provider_endpoint", lambda endpoint: None)
    result = valid_result()
    result["action_items"][0]["source_message_ids"] = ["not-in-context"]

    with pytest.raises(AIServiceError) as error:
        asyncio.run(ContextService(FakeProvider(result)).process(ProcessRequest.model_validate(request_payload())))

    assert error.value.code == ErrorCode.OUTPUT_INVALID


def test_http_validation_does_not_echo_secret(monkeypatch):
    monkeypatch.setattr("app.main.service", ContextService(FakeProvider(valid_result())))
    invalid = request_payload()
    invalid["provider"]["api_token"] = "do-not-echo"
    invalid["context"]["messages"][0]["sender_public_user_id"] = "unknown"

    response = TestClient(app).post("/v1/process", json=invalid)

    assert response.status_code == 422
    assert "do-not-echo" not in response.text


def test_endpoint_policy_blocks_private_addresses(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    )

    with pytest.raises(AIServiceError) as error:
        endpoint_policy.validate_provider_endpoint("https://provider.example/v1/chat/completions")

    assert error.value.code == ErrorCode.ENDPOINT_NOT_ALLOWED


def test_process_requires_internal_service_token(monkeypatch):
    monkeypatch.setattr("app.main.internal_token", "internal-secret")

    response = TestClient(app).post("/v1/process", json=request_payload())

    assert response.status_code == 401
    assert "internal-secret" not in response.text