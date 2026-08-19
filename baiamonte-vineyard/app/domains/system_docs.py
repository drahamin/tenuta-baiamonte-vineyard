from __future__ import annotations

from typing import Any


def hospitality_documentation(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    users = sorted({
        str(profile.get("username") or "").strip()
        for profile in profiles.values()
        if str(profile.get("username") or "").strip()
        and (str(profile.get("access_level") or "").casefold() == "hospitality"
             or "hospitality manager" in str(profile.get("role") or "").casefold())
    })
    return {
        "service": {
            "name": "Hospitality", "port": 8101, "url": "http://192.168.0.10:8101",
            "health_url": "http://192.168.0.10:8101/health",
            "access": "Hospitality Manager or Administrator",
            "purpose": "Private experiences, guest readiness, deposits and communication history",
        },
        "api_group": {"name": "Hospitality", "routes": [
            {"method": "GET", "path": "/api/v1/hospitality/dashboard", "access": "Hospitality Manager", "purpose": "Packages, schedule, guest readiness and balances"},
            {"method": "POST/PUT", "path": "/api/v1/hospitality/packages", "access": "Hospitality Manager", "purpose": "Create or update experience packages"},
            {"method": "POST/PUT", "path": "/api/v1/hospitality/reservations", "access": "Hospitality Manager", "purpose": "Create or update private experiences"},
            {"method": "POST", "path": "/api/v1/hospitality/reservations/{id}/communication", "access": "Hospitality Manager", "purpose": "Explicitly send or record guest communication"},
        ]},
        "access_profile": {
            "name": "Hospitality Managers", "users": users,
            "scope": "Private experiences, packages, guest readiness, deposits and confirmations",
        },
        "notes": [
            "Home Assistant is authoritative for identity; Vineyard Operations is authoritative for access, roles and approvals.",
            "Hospitality permits one confirmed private guest party at a time; guest contact data is excluded from TV feeds.",
        ],
    }
