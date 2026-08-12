"""Mirror Baiamonte Google Calendar and Tasks from Home Assistant into MariaDB."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any

from .config import get_settings, runtime_option
from .db import fetch_all, fetch_one, transaction
from .ha_auth import home_assistant_token
from .service import estate_id, json_ready


HA_BASES = ("http://supervisor/core/api", "http://homeassistant:8123/api", "http://core-homeassistant:8123/api")


def _request(path: str, *, payload: dict[str, Any] | None = None) -> Any:
    token = home_assistant_token()
    if not token:
        raise RuntimeError("Home Assistant API token is unavailable")
    last_error: Exception | None = None
    for base in HA_BASES:
        try:
            request = urllib.request.Request(
                base + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                method="POST" if payload is not None else "GET",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read() or b"null")
        except Exception as error:
            last_error = error
    raise RuntimeError(f"Home Assistant planning request failed: {last_error}")


def _states() -> list[dict[str, Any]]:
    result = _request("/states")
    return result if isinstance(result, list) else []


def _entities(states: list[dict[str, Any]], domain: str, configured: str) -> tuple[list[str], str]:
    state_map = {str(item.get("entity_id") or ""): item for item in states}
    explicit = list(dict.fromkeys(value.strip() for value in configured.split(",") if value.strip().startswith(domain + ".")))
    if explicit:
        valid = [entity_id for entity_id in explicit if entity_id in state_map]
        return (valid, "configured") if valid else ([], "configured entity not found")
    named, available = [], []
    for entity_id, item in state_map.items():
        if not entity_id.startswith(domain + ".") or item.get("state") in {None, "unknown", "unavailable"}:
            continue
        available.append(entity_id)
        attributes = item.get("attributes") or {}
        text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold()
        if any(term in text for term in ("baiamonte", "vineyard", "vigneto", "tenuta")):
            named.append(entity_id)
    if named:
        return named, "discovered by vineyard name"
    if len(available) == 1:
        return available, "only available entity"
    return [], f"{len(available)} available; choose explicitly" if available else "none available"


def _service(domain: str, service: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = _request(f"/services/{domain}/{service}?return_response", payload=payload)
    if not isinstance(result, dict):
        return {}
    response = result.get("service_response", result)
    return response if isinstance(response, dict) else {}


def _calendar_events(entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"start": start.isoformat(), "end": end.isoformat()})
    try:
        result = _request(f"/calendars/{urllib.parse.quote(entity_id, safe='')}?{query}")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
    except Exception:
        pass
    response = _service("calendar", "get_events", {"entity_id": [entity_id], "start_date_time": start.isoformat(), "end_date_time": end.isoformat()})
    return [item for item in ((response.get(entity_id) or {}).get("events") or []) if isinstance(item, dict)]


def _todo_items(entity_id: str) -> list[dict[str, Any]]:
    response = _service("todo", "get_items", {"entity_id": [entity_id]})
    entity_result = response.get(entity_id) or {}
    return [item for item in (entity_result.get("items") or []) if isinstance(item, dict)]


def _value(value: Any) -> Any:
    return value.get("dateTime") or value.get("date") if isinstance(value, dict) else value


def _datetime(value: Any) -> datetime | None:
    value = _value(value)
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text[:10]), time.min)
        except ValueError:
            return None
    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _external_key(source_type: str, entity_id: str, item: dict[str, Any]) -> str:
    stable = item.get("uid") or item.get("id") or item.get("event_id")
    occurrence = _value(item.get("start")) if source_type == "calendar" else _value(item.get("due"))
    material = [source_type, entity_id, stable or "", occurrence or "", item.get("summary") or item.get("item") or ""]
    return hashlib.sha256("\x1f".join(map(str, material)).encode()).hexdigest()


def sync_google_planning() -> dict[str, Any]:
    """Fetch, upsert and deactivate a bounded mirror without creating duplicate work records."""
    settings = get_settings()
    states = _states()
    calendar_ids, calendar_source = _entities(states, "calendar", str(runtime_option("planning_calendar_entities", settings.planning_calendar_entities)))
    todo_ids, todo_source = _entities(states, "todo", str(runtime_option("planning_todo_entities", settings.planning_todo_entities)))
    now = datetime.now().astimezone()
    start, end = now - timedelta(days=45), now + timedelta(days=400)
    fetched: list[tuple[str, str, dict[str, Any]]] = []
    errors: dict[str, str] = {}
    queried: set[tuple[str, str]] = set()
    for entity_id in calendar_ids:
        try:
            fetched.extend(("calendar", entity_id, item) for item in _calendar_events(entity_id, start, end))
            queried.add(("calendar", entity_id))
        except Exception as error:
            errors[entity_id] = str(error)[:300]
    for entity_id in todo_ids:
        try:
            fetched.extend(("todo", entity_id, item) for item in _todo_items(entity_id))
            queried.add(("todo", entity_id))
        except Exception as error:
            errors[entity_id] = str(error)[:300]
    seen: dict[tuple[str, str], set[str]] = {source: set() for source in queried}
    with transaction() as (_, cursor):
        for source_type, entity_id, item in fetched:
            key = _external_key(source_type, entity_id, item)
            seen.setdefault((source_type, entity_id), set()).add(key)
            cursor.execute(
                "INSERT INTO external_planning_items (estate_id,source_type,source_entity,external_key,title,description,location,starts_at,ends_at,due_at,item_status,raw_payload,last_seen_at,active) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),1) ON DUPLICATE KEY UPDATE title=VALUES(title),description=VALUES(description),location=VALUES(location),starts_at=VALUES(starts_at),ends_at=VALUES(ends_at),due_at=VALUES(due_at),item_status=VALUES(item_status),raw_payload=VALUES(raw_payload),last_seen_at=NOW(),active=1",
                (estate_id(), source_type, entity_id, key, str(item.get("summary") or item.get("item") or "Untitled")[:500], item.get("description"), item.get("location"), _datetime(item.get("start")), _datetime(item.get("end")), _datetime(item.get("due")), item.get("status"), json.dumps(json_ready(item))),
            )
        for (source_type, entity_id), keys in seen.items():
            if keys:
                placeholders = ",".join(["%s"] * len(keys))
                cursor.execute(f"UPDATE external_planning_items SET active=0 WHERE estate_id=%s AND source_type=%s AND source_entity=%s AND external_key NOT IN ({placeholders})", (estate_id(), source_type, entity_id, *keys))
            else:
                cursor.execute("UPDATE external_planning_items SET active=0 WHERE estate_id=%s AND source_type=%s AND source_entity=%s", (estate_id(), source_type, entity_id))
        metadata = {"calendar_entities": calendar_ids, "todo_entities": todo_ids, "calendar_source": calendar_source, "todo_source": todo_source, "items": len(fetched), "errors": errors}
        cursor.execute(
            "INSERT INTO sync_checkpoints (estate_id,integration_name,checkpoint_value,last_success_at,last_attempt_at,last_error,metadata) VALUES (%s,'google-planning',%s,%s,NOW(),%s,%s) ON DUPLICATE KEY UPDATE checkpoint_value=VALUES(checkpoint_value),last_success_at=VALUES(last_success_at),last_attempt_at=NOW(),last_error=VALUES(last_error),metadata=VALUES(metadata)",
            (estate_id(), now.isoformat(), None if errors else datetime.now(), json.dumps(errors) if errors else None, json.dumps(metadata)),
        )
    if errors and not fetched:
        raise RuntimeError("; ".join(f"{key}: {value}" for key, value in errors.items()))
    return {"calendar_entities": calendar_ids, "todo_entities": todo_ids, "calendar_source": calendar_source, "todo_source": todo_source, "stored": len(fetched), "errors": errors}


def planning_view() -> dict[str, Any]:
    checkpoint = fetch_one("SELECT last_success_at,last_attempt_at,last_error,metadata FROM sync_checkpoints WHERE estate_id=%s AND integration_name='google-planning'", (estate_id(),)) or {}
    events = fetch_all("SELECT source_entity,title summary,description,location,starts_at start,ends_at end FROM external_planning_items WHERE estate_id=%s AND source_type='calendar' AND active=1 AND (ends_at IS NULL OR ends_at>=NOW()-INTERVAL 1 DAY) ORDER BY starts_at LIMIT 80", (estate_id(),))
    items = fetch_all("SELECT source_entity,title summary,description,due_at due,item_status status FROM external_planning_items WHERE estate_id=%s AND source_type='todo' AND active=1 ORDER BY item_status='completed',due_at IS NULL,due_at,title LIMIT 80", (estate_id(),))
    try:
        metadata = json.loads(checkpoint.get("metadata") or "{}")
    except (TypeError, ValueError):
        metadata = {}
    error = checkpoint.get("last_error")
    return {"calendar_entities": metadata.get("calendar_entities") or [], "todo_entities": metadata.get("todo_entities") or [], "events": json_ready(events), "items": json_ready(items), "calendar_connected": bool(checkpoint.get("last_success_at") and metadata.get("calendar_entities") and not error), "tasks_connected": bool(checkpoint.get("last_success_at") and metadata.get("todo_entities") and not error), "calendar_status": metadata.get("calendar_source") or "not synced", "tasks_status": metadata.get("todo_source") or "not synced", "last_sync_at": checkpoint.get("last_success_at"), "last_attempt_at": checkpoint.get("last_attempt_at"), "error": error}
