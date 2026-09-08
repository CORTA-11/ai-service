from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


MAX_MESSAGES = 500
MAX_MESSAGE_TEXT = 20_000
MAX_CONTEXT_BYTES = 1_000_000
MAX_REQUEST_BYTES = 1_200_000
MAX_PROVIDER_RESPONSE_BYTES = 2_000_000
MAX_CONCURRENT_PROVIDER_CALLS = 10
MAX_ACTION_ITEMS = 50
MAX_TEXT = 4_000

Priority = Literal["low", "medium", "high", "urgent"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProviderConfig(StrictModel):
    protocol: Literal["openai_chat_completions_v1"]
    endpoint_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_token: str = Field(min_length=1, max_length=8_000)
    structured_output: bool = True


class Participant(StrictModel):
    public_user_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class ChatMessage(StrictModel):
    public_message_id: str = Field(min_length=1, max_length=200)
    sender_public_user_id: str = Field(min_length=1, max_length=200)
    timestamp: datetime
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_TEXT)


class ChatContext(StrictModel):
    organization_public_id: str = Field(min_length=1, max_length=200)
    team_public_id: str = Field(min_length=1, max_length=200)
    reference_timestamp: datetime
    timezone: str = Field(min_length=1, max_length=100)
    participants: list[Participant] = Field(min_length=1, max_length=MAX_MESSAGES)
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)

    @model_validator(mode="after")
    def validate_context(self) -> "ChatContext":
        participant_ids = {participant.public_user_id for participant in self.participants}
        message_ids = [message.public_message_id for message in self.messages]
        if len(participant_ids) != len(self.participants):
            raise ValueError("participant IDs must be unique")
        if len(set(message_ids)) != len(message_ids):
            raise ValueError("message IDs must be unique")
        if any(message.sender_public_user_id not in participant_ids for message in self.messages):
            raise ValueError("message sender must be a participant")
        return self


class ProcessingOptions(StrictModel):
    response_language: str = Field(default="en", min_length=2, max_length=20)
    max_action_items: int = Field(default=10, ge=0, le=MAX_ACTION_ITEMS)


class ProcessRequest(StrictModel):
    schema_version: Literal["1"]
    request_id: UUID
    operation: Literal["chat_summary_and_actions"]
    provider: ProviderConfig
    context: ChatContext
    options: ProcessingOptions = Field(default_factory=ProcessingOptions)

    @model_validator(mode="after")
    def validate_size(self) -> "ProcessRequest":
        serialized_size = len(self.model_dump_json().encode("utf-8"))
        if serialized_size > MAX_REQUEST_BYTES:
            raise ValueError("request exceeds maximum serialized size")
        context_size = len(self.context.model_dump_json().encode("utf-8"))
        if context_size > MAX_CONTEXT_BYTES:
            raise ValueError("chat context exceeds maximum serialized size")
        return self


class Decision(StrictModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    source_message_ids: list[str] = Field(min_length=1, max_length=MAX_MESSAGES)


class Summary(StrictModel):
    overview: str = Field(min_length=1, max_length=MAX_TEXT)
    key_points: list[str] = Field(max_length=MAX_MESSAGES)
    decisions: list[Decision] = Field(max_length=MAX_MESSAGES)
    open_questions: list[str] = Field(max_length=MAX_MESSAGES)


class ModelActionItem(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=MAX_TEXT)
    assignee_user_id: str | None = Field(default=None, max_length=200)
    priority: Priority | None = None
    due_date: date | None = None
    source_message_ids: list[str] = Field(min_length=1, max_length=MAX_MESSAGES)
    confidence: float = Field(ge=0.0, le=1.0)


class ModelResult(StrictModel):
    schema_version: Literal["1"]
    summary: Summary
    action_items: list[ModelActionItem] = Field(max_length=MAX_ACTION_ITEMS)


class CandidateActionItem(ModelActionItem):
    candidate_id: UUID


class ProcessResponse(StrictModel):
    schema_version: Literal["1"]
    request_id: UUID
    summary: Summary
    action_items: list[CandidateActionItem]