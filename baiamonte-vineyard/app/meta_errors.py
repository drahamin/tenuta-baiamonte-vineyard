from __future__ import annotations

import json
import re
import urllib.error


def meta_error(error: Exception) -> str:
    """Return Meta's safe, actionable error fields without request credentials."""
    if isinstance(error, urllib.error.HTTPError):
        try:
            payload = json.loads(error.read() or b"{}")
            detail = payload.get("error") or {}
            error_data = detail.get("error_data") if isinstance(detail.get("error_data"), dict) else {}
            candidates = (
                detail.get("error_user_title"),
                detail.get("error_user_msg"),
                error_data.get("details"),
                detail.get("message"),
            )
            parts: list[str] = []
            for value in candidates:
                text = re.sub(r"\s+", " ", str(value or "")).strip()
                if text and text not in parts:
                    parts.append(text)
            code = detail.get("code")
            subcode = detail.get("error_subcode")
            if code is not None:
                reference = f"Meta code {code}" + (f"/{subcode}" if subcode is not None else "")
                if not any(reference.lower() in item.lower() for item in parts):
                    parts.append(reference)
            return " · ".join(parts)[:700] or str(error)[:500]
        except Exception:
            pass
    return str(error)[:500]
