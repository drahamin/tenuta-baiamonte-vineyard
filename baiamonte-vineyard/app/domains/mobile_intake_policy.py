"""Exact, default-off identity boundary for the first mobile intake pilot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from .. import access
from ..config import get_settings, runtime_option


INITIAL_KINDS = frozenset({"enology_reading"})


@dataclass(frozen=True)
class MobileIntakeAuthorPolicy:
    website_user_id: str
    website_username: str
    ha_user_id: str
    ha_username: str
    allowed_kinds: frozenset[str]

    @classmethod
    def current(cls) -> "MobileIntakeAuthorPolicy":
        raw = runtime_option("remote_mobile_intake_author_policy", get_settings().remote_mobile_intake_author_policy)
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            raise HTTPException(503, "Mobile intake pilot is not enabled")
        values = (
            str(raw.get("website_user_id") or "").strip().lower(),
            str(raw.get("website_username") or "").strip().casefold(),
            str(raw.get("ha_user_id") or "").strip().lower(),
            str(raw.get("ha_username") or "").strip().casefold(),
        )
        kinds = frozenset(str(item).strip() for item in raw.get("allowed_kinds") or [] if str(item).strip())
        if not _uuid(values[0]) or not values[1] or not _ha_id(values[2]) or not values[3] or kinds != INITIAL_KINDS:
            raise HTTPException(503, "Mobile intake pilot policy is invalid")
        return cls(*values, kinds)

    def request_is_author(self, request: Request) -> bool:
        settings = get_settings()
        if any(key.lower() == b"x-api-key" for key, _value in request.scope.get("headers", [])):
            return False
        ingress_path = _single_header(request, b"x-ingress-path")
        username = _single_header(request, b"x-remote-user-name")
        user_id = _single_header(request, b"x-remote-user-id")
        return (
            settings.trust_home_assistant_ingress
            and ingress_path.startswith("/api/hassio_ingress/")
            and access.trusted_ingress_request(request)
            and username.strip().casefold() == self.ha_username
            and user_id.strip().lower() == self.ha_user_id
        )

    def sync_actor_is_author(self, actor: dict[str, Any], kind: str) -> bool:
        return (
            str(actor.get("user_id") or "").strip().lower() == self.website_user_id
            and str(actor.get("username") or "").strip().casefold() == self.website_username
            and str(actor.get("ha_user_id") or "").strip().lower() == self.ha_user_id
            and kind in self.allowed_kinds
        )

    def require_author_request(self, request: Request) -> str:
        if not self.request_is_author(request):
            raise HTTPException(403, "Mobile intake is limited to the approved author")
        return self.website_username


def review_unavailable() -> None:
    """The first pilot ends at pending review; no human decision route is active."""
    raise HTTPException(503, "Mobile intake review is not enabled")


def _uuid(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value) is not None


def _ha_id(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _single_header(request: Request, name: bytes) -> str:
    """Return one unambiguous trusted-proxy header; duplicates fail closed."""
    values = [value for key, value in request.scope.get("headers", []) if key.lower() == name]
    if len(values) != 1:
        return ""
    try:
        return values[0].decode("latin-1")
    except UnicodeDecodeError:
        return ""
