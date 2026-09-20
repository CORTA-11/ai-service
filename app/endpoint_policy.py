import ipaddress
import socket
from urllib.parse import urlparse

from .errors import AIServiceError, ErrorCode


def validate_provider_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AIServiceError(ErrorCode.ENDPOINT_NOT_ALLOWED, "provider endpoint is not allowed", 400)
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise AIServiceError(ErrorCode.ENDPOINT_NOT_ALLOWED, "provider endpoint is not reachable", 400) from exc
    if not addresses or any(_is_blocked_address(address) for address in addresses):
        raise AIServiceError(ErrorCode.ENDPOINT_NOT_ALLOWED, "provider endpoint is not allowed", 400)


def _is_blocked_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified))