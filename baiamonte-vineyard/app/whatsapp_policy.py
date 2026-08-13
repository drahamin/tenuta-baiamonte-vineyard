import re
from typing import Any


def approved_whatsapp_template(templates: list[dict[str, Any]], name: str, language: str = "") -> dict[str, Any] | None:
    """Resolve only an exact Meta-approved template and language combination."""
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "", name or "")
    clean_language = (language or "").strip()[:12]
    matches = [
        item for item in templates
        if str(item.get("status") or "").upper() == "APPROVED"
        and str(item.get("name") or "") == clean_name
        and "{{" not in str(item.get("components") or "")
    ]
    if clean_language:
        return next((item for item in matches if str(item.get("language") or "") == clean_language), None)
    return matches[0] if len(matches) == 1 else None
