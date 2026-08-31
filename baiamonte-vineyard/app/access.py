from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from .config import Settings, get_settings
from .db import fetch_one
from .intelligence import home_assistant_people
from .service import estate_id


def trusted_ingress_request(request: Request) -> bool:
    """Trust HA identity headers only when they arrive from Supervisor."""
    if not request.headers.get("X-Ingress-Path") or not request.headers.get("X-Remote-User-Name"):
        return False
    host = str(request.client.host if request.client else "")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address in ipaddress.ip_network("172.30.32.0/23")


def authorize(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if settings.trust_home_assistant_ingress and trusted_ingress_request(request):
        return
    if settings.api_key and x_api_key == settings.api_key:
        return
    raise HTTPException(status_code=401, detail="Valid API key required")


def finance_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.finance_usernames.split(",") if name.strip()}


def people_profiles() -> dict[str, dict[str, Any]]:
    """Administrator-owned links between HA People, logins and app access."""
    try:
        row = fetch_one(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='people_profiles'",
            (estate_id(),),
        ) or {}
        payload = json.loads(row.get("setting_value") or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def identity_terms(*values: Any) -> set[str]:
    """Return conservative tokens used to reconnect a renamed HA Person."""
    terms: set[str] = set()
    for value in values:
        normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
        if not normalized:
            continue
        terms.add(normalized.replace(" ", "_"))
        terms.update(part for part in normalized.split() if len(part) > 2)
    return terms


def match_home_assistant_person(
    spec: dict[str, Any],
    ha_people: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
    claimed: set[str] | None = None,
) -> dict[str, Any]:
    """Match app metadata to the authoritative HA Person without duplicates."""
    profile = profile or {}
    claimed = claimed or set()
    expected_entity = str(spec.get("person_entity") or "")
    exact = next((item for item in ha_people if item.get("entity_id") == expected_entity), None)
    if exact and expected_entity not in claimed:
        return exact

    expected_user_id = str(profile.get("ha_user_id") or spec.get("ha_user_id") or "").strip()
    if expected_user_id:
        by_user = next(
            (
                item for item in ha_people
                if item.get("entity_id") not in claimed
                and str((item.get("attributes") or {}).get("user_id") or "").strip() == expected_user_id
            ),
            None,
        )
        if by_user:
            return by_user

    wanted = identity_terms(
        spec.get("key"), spec.get("username"), spec.get("name"),
        expected_entity.removeprefix("person."), *(spec.get("name_aliases") or ()),
    )
    candidates = []
    for item in ha_people:
        entity_id = str(item.get("entity_id") or "")
        if not entity_id or entity_id in claimed:
            continue
        attributes = item.get("attributes") or {}
        overlap = wanted & identity_terms(entity_id.removeprefix("person."), attributes.get("friendly_name"))
        if overlap:
            candidates.append((len(overlap), item))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    if candidates and (len(candidates) == 1 or candidates[0][0] > candidates[1][0]):
        return candidates[0][1]
    return {}


def profile_access_level(username: str) -> str | None:
    normalized = username.strip().casefold()
    for profile in people_profiles().values():
        if str(profile.get("username") or "").strip().casefold() == normalized:
            level = str(profile.get("access_level") or "").strip().casefold()
            return level if level in {"admin", "operations", "hospitality", "register", "worker", "contractor", "viewer", "none"} else None
    return None


def admin_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.admin_usernames.split(",") if name.strip()}


def operations_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.operations_usernames.split(",") if name.strip()}


def viewer_usernames(settings: Settings) -> set[str]:
    configured = {name.strip().casefold() for name in settings.viewer_usernames.split(",") if name.strip()}
    return configured | {"display", "tv", "ipad"}


def worker_accounts(settings: Settings) -> dict[str, str]:
    """Map HA usernames to authoritative HA Person names for labor entry."""
    result: dict[str, str] = {}
    for item in settings.worker_usernames.split(","):
        username, separator, display_name = item.strip().partition(":")
        if username:
            result[username.casefold()] = (display_name if separator else username).strip()
    profiles = people_profiles()
    ha_people = home_assistant_people()
    claimed: set[str] = set()
    for person_entity, profile in profiles.items():
        username = str(profile.get("username") or "").strip().casefold()
        if not username:
            continue
        if profile.get("access_level") in {"worker", "contractor"}:
            person = match_home_assistant_person(
                {"person_entity": person_entity, "username": username, "name": profile.get("name")},
                ha_people,
                profile,
                claimed,
            )
            if person:
                claimed.add(str(person.get("entity_id") or ""))
            attributes = person.get("attributes") or {}
            result[username] = str(
                attributes.get("friendly_name") or profile.get("name") or result.get(username) or username
            ).strip()
        else:
            result.pop(username, None)
    return result


def dedicated_worker_usernames(settings: Settings) -> set[str]:
    """Accounts routed only to the small clock-in workspace."""
    configured = {name.strip().casefold() for name in settings.dedicated_worker_usernames.split(",") if name.strip()}
    saved = people_profiles()
    profiles = {
        str(profile.get("username") or "").strip().casefold()
        for profile in saved.values()
        if profile.get("access_level") in {"worker", "contractor"}
    }
    overridden = {
        str(profile.get("username") or "").strip().casefold()
        for profile in saved.values()
        if profile.get("username") and profile.get("access_level") not in {"worker", "contractor"}
    }
    return (configured | {"mattia", "carmela", "carmella"} | profiles) - overridden


def request_username(request: Request) -> str:
    return (request.headers.get("X-Remote-User-Name") or "api").strip().casefold()


def authorize_worker(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    username = request_username(request)
    if (
        (settings.api_key and x_api_key == settings.api_key)
        or profile_access_level(username) in {"worker", "contractor"}
        or username in worker_accounts(settings)
        or username == "rahamin"
    ):
        return
    raise HTTPException(status_code=403, detail="This page is limited to assigned vineyard workers")


def authorize_write(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    level = profile_access_level(username)
    if level in {"admin", "operations"} or (level is None and username in operations_usernames(settings)):
        return
    raise HTTPException(status_code=403, detail="This Home Assistant account has view-only vineyard access")


def authorize_hospitality(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = request_username(request)
    level = profile_access_level(username)
    if username in admin_usernames(settings):
        return
    profile = next(
        (item for item in people_profiles().values() if str(item.get("username") or "").strip().casefold() == username),
        {},
    )
    if level in {"admin", "hospitality"} or "hospitality manager" in str(profile.get("role") or "").casefold():
        return
    raise HTTPException(status_code=403, detail="Hospitality access is limited to assigned Hospitality Managers")


def authorize_register(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Limit sales and payment access to explicitly trusted estate roles."""
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = request_username(request)
    level = profile_access_level(username)
    if username in admin_usernames(settings):
        return
    profile = next(
        (item for item in people_profiles().values() if str(item.get("username") or "").strip().casefold() == username),
        {},
    )
    role = str(profile.get("role") or "").casefold()
    if level in {"admin", "register", "hospitality"} or "hospitality manager" in role or "register" in role or "cashier" in role:
        return
    raise HTTPException(status_code=403, detail="Register access is limited to assigned sales staff")


def authorize_finance(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if has_finance_access(request, x_api_key, settings):
        return
    raise HTTPException(status_code=403, detail="Finance access is limited to the private finance group")


def has_finance_access(request: Request, x_api_key: str | None, settings: Settings) -> bool:
    """Return whether an already-authenticated request may receive finance data."""
    if settings.api_key and x_api_key == settings.api_key:
        return True
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    return bool(username and username in finance_usernames(settings))


def authorize_admin(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    level = profile_access_level(username)
    if level == "admin" or (level is None and username in admin_usernames(settings)):
        return
    raise HTTPException(status_code=403, detail="System controls are limited to the vineyard administrator")


def authorize_crew(
    x_crew_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.crew_entry_token or x_crew_token != settings.crew_entry_token:
        raise HTTPException(status_code=401, detail="Valid crew entry code required")
