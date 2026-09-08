import json
import asyncio
from uuid import uuid4

from pydantic import ValidationError

from .endpoint_policy import validate_provider_endpoint
from .errors import AIServiceError, ErrorCode
from .models import CandidateActionItem, MAX_CONCURRENT_PROVIDER_CALLS, ModelResult, ProcessRequest, ProcessResponse
from .provider import ProviderClient


class ContextService:
    def __init__(self, provider: ProviderClient | None = None):
        self.provider = provider or ProviderClient()
        self._provider_slots = asyncio.Semaphore(MAX_CONCURRENT_PROVIDER_CALLS)

    async def process(self, request: ProcessRequest) -> ProcessResponse:
        validate_provider_endpoint(str(request.provider.endpoint_url))
        async with self._provider_slots:
            raw_result = await self.provider.complete(request)
        try:
            result = ModelResult.model_validate_json(raw_result)
            self._validate_references(request, result)
        except (ValidationError, ValueError) as exc:
            raise AIServiceError(ErrorCode.OUTPUT_INVALID, "provider output failed validation", 502) from exc
        action_items = [CandidateActionItem(**item.model_dump(), candidate_id=uuid4()) for item in result.action_items]
        return ProcessResponse(
            schema_version="1",
            request_id=request.request_id,
            summary=result.summary,
            action_items=action_items,
        )

    @staticmethod
    def _validate_references(request: ProcessRequest, result: ModelResult) -> None:
        message_ids = {message.public_message_id for message in request.context.messages}
        participant_ids = {participant.public_user_id for participant in request.context.participants}
        references = [message_id for decision in result.summary.decisions for message_id in decision.source_message_ids]
        references.extend(message_id for item in result.action_items for message_id in item.source_message_ids)
        if any(message_id not in message_ids for message_id in references):
            raise ValueError("provider returned an unknown source message ID")
        if any(item.assignee_user_id is not None and item.assignee_user_id not in participant_ids for item in result.action_items):
            raise ValueError("provider returned an unknown assignee ID")
        if len(result.action_items) > request.options.max_action_items:
            raise ValueError("provider returned too many action items")