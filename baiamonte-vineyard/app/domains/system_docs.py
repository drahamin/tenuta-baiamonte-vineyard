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
            "purpose": "Gmail guest inquiries, private experiences, readiness, deposits and communication history",
        },
        "api_group": {"name": "Hospitality", "routes": [
            {"method": "GET", "path": "/api/v1/hospitality/dashboard", "access": "Hospitality Manager", "purpose": "Packages, schedule, guest readiness and balances"},
            {"method": "GET/PUT", "path": "/api/v1/hospitality/settings", "access": "Hospitality Manager", "purpose": "Inbound Gmail subjects and reply templates"},
            {"method": "POST", "path": "/api/v1/hospitality/inquiries/sync", "access": "Hospitality Manager", "purpose": "Check Gmail and route matching guest inquiries"},
            {"method": "GET/PUT/DELETE", "path": "/api/v1/hospitality/inquiries/{id}", "access": "Hospitality Manager", "purpose": "Review, update or remove a guest inquiry"},
            {"method": "POST", "path": "/api/v1/hospitality/inquiries/{id}/response", "access": "Hospitality Manager", "purpose": "Explicitly send an email reply"},
            {"method": "POST/PUT", "path": "/api/v1/hospitality/packages", "access": "Hospitality Manager", "purpose": "Create or update experience packages"},
            {"method": "POST/PUT/DELETE", "path": "/api/v1/hospitality/reservations", "access": "Hospitality Manager", "purpose": "Create, update or delete private experiences"},
            {"method": "POST", "path": "/api/v1/hospitality/reservations/{id}/communication", "access": "Hospitality Manager", "purpose": "Explicitly send or record guest communication"},
        ]},
        "access_profile": {
            "name": "Hospitality Managers", "users": users,
            "scope": "Guest inquiries, private experiences, packages, readiness, deposits and confirmations",
        },
        "notes": [
            "Home Assistant is authoritative for identity; Vineyard Operations is authoritative for access, roles and approvals.",
            "Hospitality permits one confirmed private guest party at a time; guest contact data is excluded from TV feeds.",
        ],
    }
