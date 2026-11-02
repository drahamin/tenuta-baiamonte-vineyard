"""Small dependency-free helpers shared by Home Assistant proxy views."""

from __future__ import annotations

from typing import Any
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import stat
import time
import urllib.parse


async def bounded_response_body(upstream: Any, limit: int = 2 * 1024 * 1024) -> bytes:
    """Read a chunked response through EOF and fail closed above ``limit``."""
    body = bytearray()
    async for chunk in upstream.content.iter_chunked(16_384):
        body.extend(chunk)
        if len(body) > limit:
            upstream.close()
            raise ValueError("response_too_large")
    return bytes(body)


def validated_mobile_target_origin(value: str) -> str:
    """Return a canonical local adapter origin or reject every URL extension."""
    parsed = urllib.parse.urlsplit(value.rstrip("/"))
    if (
        parsed.scheme != "http"
        or parsed.hostname != "0c04eef6-baiamonte-vineyard"
        or parsed.port != 8099
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("mobile gateway target must be the site-local Vineyard adapter")
    return f"http://{parsed.hostname}:8099"


def validated_mobile_exchange_hmac_key(value: str) -> str:
    """Return one exact 256-bit base64url exchange key or fail closed."""
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
        raise ValueError("mobile exchange HMAC key must be a 256-bit base64url secret")
    try:
        key = base64.urlsafe_b64decode(value + "=")
    except (ValueError, TypeError) as error:
        raise ValueError("mobile exchange HMAC key must be a 256-bit base64url secret") from error
    if len(key) != 32:
        raise ValueError("mobile exchange HMAC key must be a 256-bit base64url secret")
    return value


def load_mobile_gateway_runtime(
    config_dir: str | Path,
    *,
    require_enabled: bool = True,
) -> dict[str, str | bool]:
    """Load the add-on-managed Core relay config only from a private regular file."""
    path = Path(config_dir) / ".storage" / "baiamonte_mobile_gateway.json"
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            return {}
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 4096:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            return {}
        enabled = payload["enabled"] is True
        if require_enabled and not enabled:
            return {}
        public_host = str(payload.get("public_host") or "").casefold().strip()
        if public_host != "baiamonte.rhmproxy.com":
            return {}
        exchange_hmac_key = ""
        if enabled:
            exchange_hmac_key = validated_mobile_exchange_hmac_key(
                str(payload.get("exchange_hmac_key") or "")
            )
        return {
            "enabled": enabled,
            "public_host": public_host,
            "target_origin": validated_mobile_target_origin(str(payload.get("target_origin") or "")),
            "exchange_hmac_key": exchange_hmac_key,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def signed_exchange_headers(
    secret: str,
    user_id: str,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build a request-bound Core-to-Vineyard exchange proof."""
    secret = validated_mobile_exchange_hmac_key(secret)
    key = base64.urlsafe_b64decode(secret + "=")
    issued_at = int(time.time()) if timestamp is None else int(timestamp)
    request_nonce = nonce or secrets.token_urlsafe(24)
    if re.fullmatch(r"[A-Za-z0-9_-]{24,64}", request_nonce) is None:
        raise ValueError("mobile exchange nonce is invalid")
    canonical = f"POST\n/api/v1/mobile/session/exchange\n{issued_at}\n{request_nonce}\n{user_id}\n"
    signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Baiamonte-Mobile-Timestamp": str(issued_at),
        "X-Baiamonte-Mobile-Nonce": request_nonce,
        "X-Baiamonte-Mobile-Signature": signature,
    }
