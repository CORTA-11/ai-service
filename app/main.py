import hmac
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import AIServiceError, ErrorCode
from .models import MAX_REQUEST_BYTES, ProcessRequest
from .service import ContextService


app = FastAPI(title="Synodus AI Context Engine", version="1.0.0")
service = ContextService()
internal_token = os.getenv("AI_SERVICE_TOKEN", "")


@app.middleware("http")
async def enforce_request_size(request: Request, call_next):
    if request.url.path == "/v1/process" and internal_token and not hmac.compare_digest(request.headers.get("x-synodus-ai-token", ""), internal_token):
        return _error_response(AIServiceError(ErrorCode.INVALID_REQUEST, "service authentication failed", 401))
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            return _error_response(AIServiceError(ErrorCode.INVALID_REQUEST, "invalid content length", 400))
        if declared_length < 0:
            return _error_response(AIServiceError(ErrorCode.INVALID_REQUEST, "invalid content length", 400))
        if declared_length > MAX_REQUEST_BYTES:
            return _error_response(AIServiceError(ErrorCode.CONTEXT_TOO_LARGE, "request is too large", 413))
    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        return _error_response(AIServiceError(ErrorCode.CONTEXT_TOO_LARGE, "request is too large", 413))

    body_sent = False

    async def receive():
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        body_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return await call_next(Request(request.scope, receive=receive))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    error_types = {error.get("type") for error in exc.errors()}
    if "context_too_large" in error_types or "request_too_large" in error_types:
        return _error_response(AIServiceError(ErrorCode.CONTEXT_TOO_LARGE, "request is too large", 413))
    if "provider_protocol_unsupported" in error_types:
        return _error_response(AIServiceError(ErrorCode.PROTOCOL_UNSUPPORTED, "provider protocol is not supported", 400))
    return _error_response(AIServiceError(ErrorCode.INVALID_REQUEST, "request validation failed", 422))


@app.exception_handler(AIServiceError)
async def service_error_handler(request: Request, exc: AIServiceError):
    return _error_response(exc)


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    return {"status": "ok"}


@app.post("/v1/process")
async def process(request: ProcessRequest):
    return await service.process(request)


def _error_response(error: AIServiceError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code, "message": error.message}})