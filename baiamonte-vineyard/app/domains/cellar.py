from __future__ import annotations


def manual_tank_definitions(raw: object, limit: int = 8) -> list[list[str]]:
    """Normalize the legacy configured tank string for one-time migration."""
    values = [part.strip() for part in str(raw or "").split(",") if part.strip()][:limit]
    return [[value.strip() for value in definition.split("|")] for definition in values]
