from __future__ import annotations

import json

from fastapi import HTTPException, Request

from ..access import admin_usernames, people_profiles, profile_access_level, request_username
from ..config import get_settings
from ..db import transaction
from ..service import audit, estate_id


ESTATE_ROLES = (
    "Owner / Principal", "Estate administrator", "Estate manager",
    "Agronomist", "Enologist", "Agronomist & Enologist", "Accountant",
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
