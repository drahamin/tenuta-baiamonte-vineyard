from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request

from ..access import admin_usernames, dedicated_worker_usernames, finance_usernames, operations_usernames, people_profiles, profile_access_level, request_username, viewer_usernames, worker_accounts
from ..config import get_settings
from ..db import transaction
from ..service import audit, estate_id


ESTATE_ROLES = (
    "Owner / Principal", "Estate administrator", "Estate manager",
    "Agronomist", "Enologist", "Agronomist & Enologist", "Hospitality Manager", "Register / Cashier", "Accountant",
    "Operations", "Vineyard worker", "Cellar worker", "Year-round contractor",
    "Seasonal labor", "Team member", "Display / kiosk",
)


def role_approval_permissions(role: str, access_level: str | None = None) -> dict[str, bool]:
    normalized = str(role or "").casefold()
    administrator = access_level == "admin"
    return {
        "agronomy": administrator or "agronomist" in normalized,
        "enology": administrator or "enologist" in normalized,
    }


def sync_ingress_identity(request: Request) -> None:
    """Mirror HA identity while leaving estate roles and approvals app-owned."""
    username = request_username(request)
    user_id = str(request.headers.get("X-Remote-User-Id") or "").strip()
    display_name = str(request.headers.get("X-Remote-User-Display-Name") or "").strip()
    if username == "api" or not (username or user_id):
        return
    profiles = people_profiles()
    match = next(((entity, profile) for entity, profile in profiles.items()
                  if user_id and str(profile.get("ha_user_id") or "") == user_id), None)
    if not match:
        match = next(((entity, profile) for entity, profile in profiles.items()
                      if str(profile.get("username") or "").strip().casefold() == username), None)
    if not match:
        return
    entity_id, profile = match
    updated = {**profile, "username": username}
    if user_id:
        updated["ha_user_id"] = user_id
    if display_name:
        updated["name"] = display_name
    if updated == profile:
        return
    profiles[entity_id] = updated
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'people_profiles',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(profiles, ensure_ascii=False, default=str)),
        )
        audit(cursor, "sync_identity", "person_profile", entity_id, {
            "username": username, "ha_user_id": user_id or None, "name": display_name or None,
        }, username)


def require_discipline_approval(request: Request, discipline: str) -> None:
    username = request_username(request)
    profile = next((item for item in people_profiles().values()
                    if str(item.get("username") or "").strip().casefold() == username), {})
    role = str(profile.get("role") or ("Agronomist & Enologist" if username == "sebastian" else ""))
    access_level = "admin" if username in admin_usernames(get_settings()) else profile_access_level(username)
    if role_approval_permissions(role, access_level).get(discipline):
        return
    label = "Agronomist" if discipline == "agronomy" else "Enologist"
    raise HTTPException(403, f"{label} approval is required for this decision")


def worker_profile(name: str) -> dict[str, str]:
    key = name.casefold()
    saved = next((profile for profile in people_profiles().values()
                  if str(profile.get("name") or "").strip().casefold() == key), {})
    saved_role = str(saved.get("role") or "").strip()
    if saved_role:
        return {"role": saved_role, "payroll_scope": "part_time" if saved_role == "Estate manager" else "contractor"}
    if "giancarlo" in key:
        return {"role": "Estate manager", "payroll_scope": "part_time"}
    if "luca" in key:
        return {"role": "Year-round contractor", "payroll_scope": "contractor"}
    return {"role": "Seasonal labor", "payroll_scope": "contractor"}


def natural_person_first_name(display_name: str | None) -> str | None:
    """Return a safe first name only when HA supplied a full human name."""
    value = " ".join(str(display_name or "").strip().split())
    parts = value.split()
    if not 2 <= len(parts) <= 5:
        return None
    system_terms = {
        "admin", "api", "bot", "display", "fully", "guest", "home", "kiosk",
        "mqtt", "register", "root", "service", "system", "tablet", "tv",
    }
    for part in parts:
        word = part.strip(".'’-")
        if not word or not word.replace("-", "").replace("'", "").replace("’", "").isalpha():
            return None
        if word.casefold() in system_terms:
            return None
    return parts[0].strip(".'’-") or None


def session_payload(request: Request, settings: Any) -> dict[str, Any]:
    username = (request.headers.get("X-Remote-User-Name") or "api").strip()
    display_name_header = request.headers.get("X-Remote-User-Display-Name")
    normalized = username.casefold()
    sync_ingress_identity(request)
    workers = worker_accounts(settings)
    level = profile_access_level(normalized)
    linked = next((profile for profile in people_profiles().values()
                   if str(profile.get("username") or "").strip().casefold() == normalized), {})
    is_worker = level == "worker" or (level is None and normalized in workers)
    dedicated_worker = level == "worker" if level is not None else normalized in dedicated_worker_usernames(settings)
    hourly = bool(linked.get("track_hourly_labor")) if linked else normalized in dedicated_worker_usernames(settings)
    is_admin = level == "admin" or (level is None and normalized in admin_usernames(settings)) or username == "api"
    operations = is_admin or level in {"operations", "viewer"} or (level is None and normalized in (operations_usernames(settings) | viewer_usernames(settings)))
    role = str(linked.get("role") or ("Agronomist & Enologist" if normalized == "sebastian" else ""))
    hospitality = is_admin or level == "hospitality" or "hospitality manager" in role.casefold()
    register = is_admin or level in {"register", "hospitality"} or "hospitality manager" in role.casefold() or "register" in role.casefold() or "cashier" in role.casefold()
    can_view = level in {"admin", "operations", "hospitality", "register", "worker", "viewer"} or (level is None and (operations or is_worker))
    can_write = level in {"admin", "operations"} or (level is None and normalized in operations_usernames(settings))
    return {
        "username": username, "display_name": display_name_header or username,
        "greeting_first_name": natural_person_first_name(display_name_header),
        "estate_role": role or None, "approval_permissions": role_approval_permissions(role, "admin" if is_admin else level),
        "permissions": {
            "view": can_view, "write": can_write and not dedicated_worker,
            "finance": normalized in finance_usernames(settings), "hospitality": hospitality, "register": register,
            "operations_workspace": operations, "admin": is_admin, "worker": is_worker,
            "hourly_worker": hourly, "dedicated_worker": dedicated_worker,
        },
        "worker_name": workers.get(normalized),
    }
