import json
import asyncio
import logging
import os
import time
from uuid import uuid4

from pydantic import ValidationError

from .endpoint_policy import validate_provider_endpoint
from .errors import AIServiceError, ErrorCode
from .models import CandidateActionItem, MAX_CONCURRENT_PROVIDER_CALLS, ModelResult, ProcessRequest, ProcessResponse
from .provider import ProviderAdapter, ProviderClient


logger = logging.getLogger("synodus.ai")


class ContextService:
    def __init__(self, provider: ProviderAdapter | None = None, max_concurrent_provider_calls: int | None = None):
        self.provider = provider or ProviderClient()
        configured_limit = int(os.getenv("AI_MAX_CONCURRENT_PROVIDER_CALLS", str(MAX_CONCURRENT_PROVIDER_CALLS)))
        self._provider_slots = asyncio.Semaphore(max_concurrent_provider_calls or max(configured_limit, 1))

    async def process(self, request: ProcessRequest) -> ProcessResponse:
        try:
            started = time.perf_counter()
            validate_provider_endpoint(str(request.provider.endpoint_url))
            async with self._provider_slots:
                raw_result = await self.provider.complete(request)
            try:
                result = ModelResult.model_validate_json(raw_result)
                self._validate_references(request, result)
            except (ValidationError, ValueError) as exc:
                raise AIServiceError(ErrorCode.OUTPUT_INVALID, "provider output failed validation", 502) from exc
            action_items = [CandidateActionItem(**item.model_dump(), candidate_id=uuid4()) for item in result.action_items]
            response = ProcessResponse(
                schema_version="1",
                request_id=request.request_id,
                summary=result.summary,
                action_items=action_items,
            )
            logger.info(
                "AI context processing completed",
                extra={
                    "request_id": str(request.request_id),
                    "operation": request.operation,
                    "provider_protocol": request.provider.protocol,
                    "model": request.provider.model,
                    "message_count": len(request.context.messages),
                    "input_size": len(request.context.model_dump_json().encode("utf-8")),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "action_item_count": len(action_items),
                },
            )
            return response
        except AIServiceError as exc:
            logger.warning(
                "AI context processing failed",
                extra={
                    "request_id": str(request.request_id),
                    "operation": request.operation,
                    "provider_protocol": request.provider.protocol,
                    "model": request.provider.model,
                    "message_count": len(request.context.messages),
                    "error_code": str(exc.code),
                },
            )
            raise

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