from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "AI_INVALID_REQUEST"
    CONTEXT_TOO_LARGE = "AI_CONTEXT_TOO_LARGE"
    ENDPOINT_NOT_ALLOWED = "AI_ENDPOINT_NOT_ALLOWED"
    PROTOCOL_UNSUPPORTED = "AI_PROVIDER_PROTOCOL_UNSUPPORTED"
    AUTH_FAILED = "AI_PROVIDER_AUTH_FAILED"
    RATE_LIMITED = "AI_PROVIDER_RATE_LIMITED"
    TIMEOUT = "AI_PROVIDER_TIMEOUT"
    BAD_RESPONSE = "AI_PROVIDER_BAD_RESPONSE"
    OUTPUT_INVALID = "AI_OUTPUT_INVALID"
    INTERNAL_ERROR = "AI_INTERNAL_ERROR"


class AIServiceError(Exception):
    def __init__(self, code: ErrorCode, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code