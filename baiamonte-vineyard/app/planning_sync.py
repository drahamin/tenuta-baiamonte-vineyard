"""Mirror Baiamonte Google Calendar and Tasks from Home Assistant into MariaDB."""

from __future__ import annotations

import hashlib
import json
import re
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Any

from .config import get_settings, runtime_option
from .db import fetch_all, fetch_one, transaction
from .ha_auth import home_assistant_token
from .service import estate_id, json_ready, new_id, season_for_year


HA_API_BASE = "http://supervisor/core/api"
APPLE_LIST_NAME = "Baiamonte"
APPLE_TREATMENTS_LIST_NAME = "Baiamonte Treatments"
WORK_MARKER_RE = re.compile(r"\[Baiamonte Work ID:\s*([0-9a-f-]{36})\]", re.I)
TREATMENT_CATEGORIES = {"treatment", "treatments", "treatment_review", "spray", "spray_application"}


def _request(path: str, *, payload: dict[str, Any] | None = None) -> Any:
    token = home_assistant_token()
    if not token:
        raise RuntimeError("Home Assistant API token is unavailable")
    last_error: Exception | None = None
    # The Supervisor Core proxy is the supported authenticated route for an
    # add-on with homeassistant_api enabled.  Hostname fallbacks bypass that
    # proxy and can turn a brief Core restart into a misleading DNS or 401
    # error, so retry the correct route instead.
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                HA_API_BASE + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                method="POST" if payload is not None else "GET",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read() or b"null")
        except Exception as error:
            last_error = error
            if attempt < 2:
                time_module.sleep(2)
    if isinstance(last_error, urllib.error.HTTPError):
        detail = f"HTTP {last_error.code}"
    elif isinstance(last_error, urllib.error.URLError):
        detail = str(last_error.reason)
    else:
        detail = type(last_error).__name__ if last_error else "unknown error"
    raise RuntimeError(f"Home Assistant planning request failed through the Supervisor proxy after 3 attempts: {detail}")


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


def _service(domain: str, service: str, payload: dict[str, Any], *, return_response: bool = True) -> dict[str, Any]:
    suffix = "?return_response" if return_response else ""
    result = _request(f"/services/{domain}/{service}{suffix}", payload=payload)
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


def _normalized_title(value: Any) -> str:
    text = re.sub(r"[^\w\s]", " ", str(value or "").casefold(), flags=re.UNICODE)
    return " ".join(text.split())[:220]


def _work_marker(task_id: str) -> str:
    return f"[Baiamonte Work ID: {task_id}]"


def _marker_task_id(description: Any) -> str | None:
    match = WORK_MARKER_RE.search(str(description or ""))
    return match.group(1) if match else None


def _clean_description(description: Any) -> str | None:
    text = WORK_MARKER_RE.sub("", str(description or "")).strip()
    return text or None


def _source_item_key(item: dict[str, Any], fallback: str) -> str:
    return str(item.get("uid") or item.get("id") or item.get("external_id") or fallback)[:255]


def _task_for_source(cursor, *, source_type: str, source_entity: str, external_key: str, title: str, description: Any) -> dict[str, Any] | None:
    marker_id = _marker_task_id(description)
    if marker_id:
        cursor.execute("SELECT * FROM tasks WHERE estate_id=%s AND id=%s", (estate_id(), marker_id))
        row = cursor.fetchone()
        if row:
            return row
    cursor.execute(
        "SELECT t.* FROM work_item_links l JOIN tasks t ON t.id=l.task_id WHERE l.estate_id=%s AND l.source_type=%s AND l.source_entity=%s AND l.external_key=%s",
        (estate_id(), source_type, source_entity, external_key),
    )
    row = cursor.fetchone()
    if row:
        return row
    normalized = _normalized_title(title)
    cursor.execute("SELECT * FROM tasks WHERE estate_id=%s AND status<>'cancelled' ORDER BY updated_at DESC LIMIT 500", (estate_id(),))
    return next((candidate for candidate in cursor.fetchall() if _normalized_title(candidate.get("title")) == normalized), None)


def _link_task(cursor, *, task_id: str, source_type: str, source_entity: str, external_key: str, title: str, status: str | None, metadata: dict[str, Any]) -> None:
    content_hash = hashlib.sha256(json.dumps(json_ready(metadata), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cursor.execute(
        "INSERT INTO work_item_links (estate_id,task_id,source_type,source_entity,external_key,normalized_title,source_status,content_hash,metadata,last_seen_at,active) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),1) ON DUPLICATE KEY UPDATE task_id=VALUES(task_id),normalized_title=VALUES(normalized_title),source_status=VALUES(source_status),content_hash=VALUES(content_hash),metadata=VALUES(metadata),last_seen_at=NOW(),active=1",
        (estate_id(), task_id, source_type, source_entity, external_key, _normalized_title(title), status, content_hash, json.dumps(json_ready(metadata))),
    )


def _merge_google_todo(cursor, entity_id: str, item: dict[str, Any], mirror_key: str) -> str:
    title = str(item.get("summary") or item.get("item") or "Untitled")[:220]
    source_key = _source_item_key(item, mirror_key)
    task = _task_for_source(cursor, source_type="google_tasks", source_entity=entity_id, external_key=source_key, title=title, description=item.get("description"))
    due = _datetime(item.get("due"))
    source_status = str(item.get("status") or "needs_action")
    status = "done" if source_status == "completed" else "planned"
    notes = _clean_description(item.get("description"))
    if task:
        task_id = task["id"]
        cursor.execute(
            "UPDATE tasks SET title=%s,due_date=COALESCE(%s,due_date),notes=COALESCE(%s,notes),status=%s,completed_at=CASE WHEN %s='done' THEN COALESCE(completed_at,NOW()) ELSE NULL END,source=CASE WHEN source='manual' THEN source ELSE 'google_tasks' END WHERE id=%s AND estate_id=%s",
            (title, due.date() if due else None, notes, status, status, task_id, estate_id()),
        )
    else:
        task_id = new_id()
        cursor.execute(
            "INSERT INTO tasks (id,estate_id,season_id,title,category,status,priority,due_date,notes,source,completed_at) VALUES (%s,%s,%s,%s,'general',%s,'normal',%s,%s,'google_tasks',%s)",
            (task_id, estate_id(), season_for_year((due or datetime.now()).year), title, status, due.date() if due else None, notes, datetime.now() if status == "done" else None),
        )
    _link_task(cursor, task_id=task_id, source_type="google_tasks", source_entity=entity_id, external_key=source_key, title=title, status=source_status, metadata=item)
    cursor.execute("UPDATE work_item_links SET active=0 WHERE estate_id=%s AND task_id=%s AND source_type='google_tasks' AND source_entity=%s AND external_key LIKE 'pending:%%'", (estate_id(), task_id, entity_id))
    return task_id


def _google_todo_entities() -> tuple[list[str], str]:
    settings = get_settings()
    return _entities(_states(), "todo", str(runtime_option("planning_todo_entities", settings.planning_todo_entities)))


def publish_task_to_google(task_id: str, entity_id: str | None = None) -> dict[str, Any]:
    task = fetch_one("SELECT * FROM tasks WHERE estate_id=%s AND id=%s", (estate_id(), task_id))
    if not task:
        raise ValueError("Task not found")
    entities, source = ([entity_id], "explicit") if entity_id else _google_todo_entities()
    if not entities:
        return {"published": False, "reason": source}
    target = entities[0]
    existing = fetch_one("SELECT external_key FROM work_item_links WHERE estate_id=%s AND task_id=%s AND source_type='google_tasks' AND source_entity=%s AND active=1 ORDER BY external_key LIKE 'pending:%%',last_seen_at DESC LIMIT 1", (estate_id(), task_id, target))
    description = "\n\n".join(value for value in (str(task.get("notes") or "").strip(), _work_marker(task_id)) if value)
    payload = {"entity_id": target, "item": task["title"], "description": description}
    if task.get("due_date"):
        payload["due_date"] = str(task["due_date"])
    if existing and not str(existing["external_key"]).startswith("pending:"):
        payload.update({"item": existing["external_key"], "rename": task["title"], "status": "completed" if task["status"] == "done" else "needs_action"})
        _service("todo", "update_item", payload, return_response=False)
        return {"published": True, "updated": True, "entity_id": target}
    _service("todo", "add_item", payload, return_response=False)
    with transaction() as (_, cursor):
        _link_task(cursor, task_id=task_id, source_type="google_tasks", source_entity=target, external_key=f"pending:{task_id}", title=task["title"], status="completed" if task["status"] == "done" else "needs_action", metadata={"pending_discovery": True, "marker": _work_marker(task_id)})
    return {"published": True, "created": True, "entity_id": target}


def _publish_missing_tasks(todo_ids: list[str]) -> list[dict[str, Any]]:
    if not todo_ids:
        return []
    rows = fetch_all(
        "SELECT t.id FROM tasks t LEFT JOIN work_item_links l ON l.estate_id=t.estate_id AND l.task_id=t.id AND l.source_type='google_tasks' AND l.source_entity=%s AND l.active=1 WHERE t.estate_id=%s AND t.status<>'cancelled' AND l.id IS NULL ORDER BY t.created_at LIMIT 100",
        (todo_ids[0], estate_id()),
    )
    results = []
    for row in rows:
        results.append(publish_task_to_google(row["id"], todo_ids[0]))
    return results


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
            if source_type == "todo":
                _merge_google_todo(cursor, entity_id, item, key)
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
    published = _publish_missing_tasks(todo_ids)
    return {"calendar_entities": calendar_ids, "todo_entities": todo_ids, "calendar_source": calendar_source, "todo_source": todo_source, "stored": len(fetched), "published": len(published), "errors": errors}


def unified_work_plan(include_completed: bool = False) -> dict[str, Any]:
    status_clause = "" if include_completed else " AND status NOT IN ('done','cancelled')"
    tasks = fetch_all(
        "SELECT t.*,b.code block_code,p.name assigned_person FROM tasks t LEFT JOIN vineyard_blocks b ON b.id=t.block_id LEFT JOIN people p ON p.id=t.assigned_person_id WHERE t.estate_id=%s" + status_clause + " ORDER BY FIELD(t.priority,'urgent','high','normal','low'),t.due_date IS NULL,t.due_date,t.title LIMIT 500",
        (estate_id(),),
    )
    links = fetch_all("SELECT task_id,source_type,source_entity,external_key,source_status,last_seen_at,active FROM work_item_links WHERE estate_id=%s AND active=1 ORDER BY last_seen_at DESC", (estate_id(),))
    by_task: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        by_task.setdefault(link["task_id"], []).append(link)
    work_items = []
    for task in tasks:
        item = dict(task)
        item["project"] = task.get("category") or "general"
        item["sources"] = by_task.get(task["id"], [])
        work_items.append(item)
    duplicate_rows = fetch_all(
        "SELECT normalized_title,source_type,source_entity,COUNT(*) item_count,GROUP_CONCAT(external_key ORDER BY external_key SEPARATOR ',') external_keys FROM work_item_links WHERE estate_id=%s AND active=1 GROUP BY normalized_title,source_type,source_entity HAVING COUNT(*)>1 ORDER BY item_count DESC,normalized_title",
        (estate_id(),),
    )
    return {
        "items": json_ready(work_items),
        "duplicates": json_ready(duplicate_rows),
        "apple_list": APPLE_LIST_NAME,
        "apple_treatments_list": APPLE_TREATMENTS_LIST_NAME,
        "apple_general_items": general_reminder_plan(include_completed=include_completed)["items"],
        "google_is_shared_store": True,
    }


def _is_treatment_task(task: dict[str, Any]) -> bool:
    category = str(task.get("category") or task.get("project") or "").strip().casefold().replace("-", "_").replace(" ", "_")
    source = str(task.get("source") or "").strip().casefold()
    title = str(task.get("title") or "").strip().casefold()
    return category in TREATMENT_CATEGORIES or category.startswith("treatment_") or source == "planned_treatment" or title.startswith("treatment plan ·")


def _task_reminder_item(task: dict[str, Any]) -> dict[str, Any]:
    notes = "\n\n".join(value for value in (str(task.get("notes") or "").strip(), _work_marker(str(task["id"]))) if value)
    return {
        "id": task["id"],
        "external_id": task["id"],
        "title": task["title"],
        "due_date": task.get("due_date"),
        "notes": notes,
        "priority": task.get("priority") or "normal",
        "status": "completed" if task.get("status") == "done" else "needs_action",
        "source": "canonical_work_plan",
    }


def general_reminder_plan(include_completed: bool = False) -> dict[str, Any]:
    """Return only non-treatment work for the Apple list named Baiamonte."""
    status_clause = "" if include_completed else " AND status NOT IN ('done','cancelled')"
    tasks = fetch_all(
        "SELECT id,title,category,status,priority,due_date,notes,source FROM tasks WHERE estate_id=%s" + status_clause + " ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date,title LIMIT 500",
        (estate_id(),),
    )
    items = [_task_reminder_item(task) for task in tasks if not _is_treatment_task(task)]
    return {
        "list": APPLE_LIST_NAME,
        "items": json_ready(items),
        "excluded_treatments": sum(1 for task in tasks if _is_treatment_task(task)),
        "guardrail": f"Only general work belongs in {APPLE_LIST_NAME}; treatments belong only in {APPLE_TREATMENTS_LIST_NAME}.",
    }


def apple_reminder_reconciliation(include_completed: bool = False) -> dict[str, Any]:
    """Return two disjoint desired lists plus exact cross-list duplicates to remove."""
    general = general_reminder_plan(include_completed=include_completed)
    treatments = treatment_reminder_plan(include_completed=include_completed)
    links = fetch_all(
        "SELECT l.source_entity,l.external_key,l.normalized_title,t.id task_id,t.title,t.category,t.source "
        "FROM work_item_links l JOIN tasks t ON t.id=l.task_id AND t.estate_id=l.estate_id "
        "WHERE l.estate_id=%s AND l.source_type='apple_reminders' AND l.active=1 "
        "AND l.source_entity IN (%s,%s) ORDER BY l.normalized_title,l.source_entity,l.external_key",
        (estate_id(), APPLE_LIST_NAME, APPLE_TREATMENTS_LIST_NAME),
    )
    remove_from_general: list[dict[str, Any]] = []
    remove_from_treatments: list[dict[str, Any]] = []
    for link in links:
        treatment = _is_treatment_task(link)
        source_list = str(link.get("source_entity") or "")
        if treatment and source_list == APPLE_LIST_NAME:
            remove_from_general.append({"external_id": link["external_key"], "title": link["title"], "wrong_list": APPLE_LIST_NAME})
        elif not treatment and source_list == APPLE_TREATMENTS_LIST_NAME:
            remove_from_treatments.append({"external_id": link["external_key"], "title": link["title"], "wrong_list": APPLE_TREATMENTS_LIST_NAME})
    return {
        "lists": {APPLE_LIST_NAME: general, APPLE_TREATMENTS_LIST_NAME: treatments},
        "remove_from_baiamonte": json_ready(remove_from_general),
        "remove_from_baiamonte_treatments": json_ready(remove_from_treatments),
        "rule": "Move or delete only the explicitly listed wrong-list copies; never recreate one reminder in both lists.",
    }


def import_apple_reminders(reminders: list[dict[str, Any]], list_name: str = APPLE_LIST_NAME) -> dict[str, Any]:
    """Merge a complete approved Apple-list snapshot into canonical work items without deleting source reminders."""
    if list_name not in {APPLE_LIST_NAME, APPLE_TREATMENTS_LIST_NAME}:
        raise ValueError("Only the Baiamonte and Baiamonte Treatments reminder lists may be synchronized")
    default_category = "treatment_review" if list_name == APPLE_TREATMENTS_LIST_NAME else "general"
    valid = [item for item in reminders if isinstance(item, dict) and str(item.get("title") or item.get("name") or "").strip()]
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in valid:
        groups.setdefault(_normalized_title(item.get("title") or item.get("name")), []).append(item)
    duplicate_ids: list[str] = []
    changed_task_ids: set[str] = set()
    seen_keys: set[str] = set()
    with transaction() as (_, cursor):
        for normalized, rows in groups.items():
            rows.sort(key=lambda row: (bool(row.get("notes")), bool(row.get("due_date") or row.get("due")), bool(row.get("priority"))), reverse=True)
            canonical = rows[0]
            title = str(canonical.get("title") or canonical.get("name"))[:220]
            source_key = _source_item_key(canonical, hashlib.sha256(normalized.encode()).hexdigest())
            task = _task_for_source(cursor, source_type="apple_reminders", source_entity=list_name, external_key=source_key, title=title, description=canonical.get("notes"))
            due = _datetime(canonical.get("due_date") or canonical.get("due"))
            completed = bool(canonical.get("completed") or canonical.get("is_completed") or str(canonical.get("status") or "").casefold() == "completed")
            notes = _clean_description(canonical.get("notes"))
            if task:
                task_id = task["id"]
                cursor.execute("UPDATE tasks SET title=%s,due_date=COALESCE(%s,due_date),notes=COALESCE(%s,notes),status=%s,completed_at=CASE WHEN %s=1 THEN COALESCE(completed_at,NOW()) ELSE completed_at END WHERE estate_id=%s AND id=%s", (title, due.date() if due else None, notes, "done" if completed else task.get("status") or "planned", int(completed), estate_id(), task_id))
            else:
                task_id = new_id()
                cursor.execute("INSERT INTO tasks (id,estate_id,season_id,title,category,status,priority,due_date,notes,source,completed_at) VALUES (%s,%s,%s,%s,%s,%s,'normal',%s,%s,'apple_reminders',%s)", (task_id, estate_id(), season_for_year((due or datetime.now()).year), title, default_category, "done" if completed else "planned", due.date() if due else None, notes, datetime.now() if completed else None))
            for index, row in enumerate(rows):
                row_key = _source_item_key(row, f"{source_key}:{index}")
                seen_keys.add(row_key)
                _link_task(cursor, task_id=task_id, source_type="apple_reminders", source_entity=list_name, external_key=row_key, title=title, status="completed" if completed else "needs_action", metadata=row)
                if index:
                    duplicate_ids.append(row_key)
            changed_task_ids.add(task_id)
        if seen_keys:
            placeholders = ",".join(["%s"] * len(seen_keys))
            cursor.execute(f"UPDATE work_item_links SET active=0 WHERE estate_id=%s AND source_type='apple_reminders' AND source_entity=%s AND external_key NOT IN ({placeholders})", (estate_id(), list_name, *seen_keys))
        else:
            cursor.execute("UPDATE work_item_links SET active=0 WHERE estate_id=%s AND source_type='apple_reminders' AND source_entity=%s", (estate_id(), list_name))
    publish_results = []
    # The general Baiamonte list participates in the shared Google work store.
    # The dedicated treatment list is intentionally isolated so it cannot
    # republish treatment reminders into general work and then round-trip them
    # back into both Apple lists.
    if list_name == APPLE_LIST_NAME:
        try:
            entities, _ = _google_todo_entities()
            for task_id in changed_task_ids:
                publish_results.append(publish_task_to_google(task_id, entities[0] if entities else None))
        except Exception as error:
            publish_results.append({"published": False, "reason": str(error)[:300]})
    return {"list": list_name, "received": len(valid), "canonical_items": len(groups), "merged_duplicates": len(duplicate_ids), "duplicate_ids_to_complete": duplicate_ids, "google_results": publish_results, "work_plan": unified_work_plan(), "list_reconciliation": apple_reminder_reconciliation()}


def treatment_reminder_plan(include_completed: bool = False) -> dict[str, Any]:
    status_clause = "" if include_completed else " AND s.status='planned'"
    rows = fetch_all(
        "SELECT s.id,s.application_date,s.purpose,s.status,s.notes,s.agronomist_approved,s.label_legal_confirmed,s.phi_checked,s.rei_checked,s.weather_checked,s.ppe_confirmed,b.code block_code FROM spray_applications s LEFT JOIN vineyard_blocks b ON b.id=s.block_id WHERE s.estate_id=%s" + status_clause + " ORDER BY s.application_date,s.purpose LIMIT 250",
        (estate_id(),),
    )
    items = []
    for row in rows:
        checks = [name for name, key in (("agronomist", "agronomist_approved"), ("label", "label_legal_confirmed"), ("PHI", "phi_checked"), ("REI", "rei_checked"), ("weather", "weather_checked"), ("PPE", "ppe_confirmed")) if row.get(key)]
        items.append({"id": row["id"], "title": f"Treatment plan · {row['purpose']}", "due_date": row["application_date"], "notes": " · ".join(filter(None, (row.get("block_code"), row.get("notes"), f"Checks recorded: {', '.join(checks)}" if checks else "Approval and safety checks pending"))), "status": "completed" if row["status"] in {"completed", "applied"} else "needs_action", "source": "planned_treatment", "may_mark_applied": False})
    return {"list": APPLE_TREATMENTS_LIST_NAME, "items": json_ready(items), "guardrail": "Reminder completion never approves or records a treatment application."}


def _easter_sunday(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(year, month, (h + l - 7 * m + 114) % 31 + 1)


def _italian_holidays(year: int) -> list[dict[str, Any]]:
    easter = _easter_sunday(year)
    fixed = [
        (1, 1, "Capodanno"), (1, 6, "Epifania"), (4, 25, "Festa della Liberazione"),
        (5, 1, "Festa dei Lavoratori"), (6, 2, "Festa della Repubblica"),
        (8, 15, "Ferragosto"), (11, 1, "Ognissanti"), (12, 8, "Immacolata Concezione"),
        (12, 25, "Natale"), (12, 26, "Santo Stefano"),
    ]
    events = [{"summary": f"Italian holiday · {name}", "start": date(year, month, day), "end": date(year, month, day), "kind": "italian_holiday", "status": "holiday"} for month, day, name in fixed]
    events.extend([
        {"summary": "Italian holiday · Pasqua", "start": easter, "end": easter, "kind": "italian_holiday", "status": "holiday"},
        {"summary": "Italian holiday · Lunedì dell'Angelo", "start": easter + timedelta(days=1), "end": easter + timedelta(days=1), "kind": "italian_holiday", "status": "holiday"},
    ])
    return events


def _operational_calendar_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in fetch_all("SELECT id,title,category,due_date,priority,status,notes FROM tasks WHERE estate_id=%s AND due_date IS NOT NULL AND status NOT IN ('done','cancelled') AND due_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE()+INTERVAL 400 DAY", (estate_id(),)):
        rows.append({"summary": task["title"], "description": task.get("notes"), "start": task["due_date"], "end": task["due_date"], "kind": "work", "status": task["status"], "priority": task["priority"], "record_id": task["id"]})
    for work in fetch_all("SELECT id,title,category,activity_date,end_date,status,notes FROM work_activities WHERE estate_id=%s AND activity_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE()+INTERVAL 400 DAY AND status='planned'", (estate_id(),)):
        rows.append({"summary": work["title"], "description": work.get("notes"), "start": work["activity_date"], "end": work.get("end_date") or work["activity_date"], "kind": "planned_work", "status": work["status"], "record_id": work["id"]})
    for treatment in fetch_all("SELECT id,purpose,application_date,status,notes FROM spray_applications WHERE estate_id=%s AND application_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE()+INTERVAL 400 DAY AND status='planned'", (estate_id(),)):
        rows.append({"summary": f"Treatment plan · {treatment['purpose']}", "description": treatment.get("notes"), "start": treatment["application_date"], "end": treatment["application_date"], "kind": "treatment_plan", "status": "planned", "record_id": treatment["id"]})
    for harvest in fetch_all("SELECT h.id,h.planned_pick_date,h.status,h.planned_kg,h.confidence,h.notes,v.name variety FROM harvest_plans h JOIN seasons s ON s.id=h.season_id JOIN grape_varieties v ON v.id=h.variety_id WHERE h.estate_id=%s AND h.planned_pick_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE()+INTERVAL 400 DAY AND h.status<>'cancelled' AND LOWER(v.name) NOT IN ('blend','other')", (estate_id(),)):
        detail = f"Projected {harvest.get('planned_kg')} kg · {harvest.get('confidence') or 'confidence not recorded'}" if harvest.get("planned_kg") is not None else harvest.get("notes")
        rows.append({"summary": f"Projected harvest · {harvest['variety']}", "description": detail, "start": harvest["planned_pick_date"], "end": harvest["planned_pick_date"], "kind": "harvest_projection", "status": harvest["status"], "record_id": harvest["id"]})
    for labor in fetch_all("SELECT id,work_date,person_or_crew,role,regular_hours,overtime_hours,notes FROM labor_entries WHERE estate_id=%s AND work_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE() ORDER BY work_date", (estate_id(),)):
        hours = float(labor.get("regular_hours") or 0) + float(labor.get("overtime_hours") or 0)
        rows.append({"summary": f"On site · {labor['person_or_crew']}", "description": f"{hours:g} recorded hours" + (f" · {labor['role']}" if labor.get("role") else ""), "start": labor["work_date"], "end": labor["work_date"], "kind": "recorded_labor", "status": "recorded", "record_id": labor["id"]})
    for issue in fetch_all("SELECT id,due_date,issue_text,priority,status,owner_text FROM issues_decisions WHERE estate_id=%s AND due_date IS NOT NULL AND status IN ('open','monitoring') AND due_date BETWEEN CURDATE()-INTERVAL 45 DAY AND CURDATE()+INTERVAL 400 DAY", (estate_id(),)):
        rows.append({"summary": f"Issue due · {issue['issue_text'][:120]}", "description": issue.get("owner_text"), "start": issue["due_date"], "end": issue["due_date"], "kind": "issue_due", "status": issue["status"], "priority": issue["priority"], "record_id": issue["id"]})
    today = date.today()
    for year in range(today.year - 1, today.year + 2):
        rows.extend(_italian_holidays(year))
    return rows


def _merge_calendar_events(google_events: list[dict[str, Any]], operational_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for event in [*google_events, *operational_events]:
        date_key = str(event.get("start") or "")[:10]
        key = (_normalized_title(event.get("summary")), date_key)
        if key in merged:
            sources = set(merged[key].get("sources") or [])
            sources.add(event.get("kind") or "google_calendar")
            merged[key]["sources"] = sorted(sources)
            if not merged[key].get("description") and event.get("description"):
                merged[key]["description"] = event["description"]
        else:
            row = dict(event)
            row["sources"] = [event.get("kind") or "google_calendar"]
            merged[key] = row
    return sorted(merged.values(), key=lambda row: (str(row.get("start") or ""), str(row.get("summary") or "")))[:200]


def planning_view() -> dict[str, Any]:
    checkpoint = fetch_one("SELECT last_success_at,last_attempt_at,last_error,metadata FROM sync_checkpoints WHERE estate_id=%s AND integration_name='google-planning'", (estate_id(),)) or {}
    google_events = fetch_all("SELECT source_entity,title summary,description,location,starts_at start,ends_at end,'google_calendar' kind FROM external_planning_items WHERE estate_id=%s AND source_type='calendar' AND active=1 AND (ends_at IS NULL OR ends_at>=NOW()-INTERVAL 1 DAY) ORDER BY starts_at LIMIT 80", (estate_id(),))
    events = _merge_calendar_events(google_events, _operational_calendar_events())
    items = fetch_all("SELECT source_entity,title summary,description,due_at due,item_status status FROM external_planning_items WHERE estate_id=%s AND source_type='todo' AND active=1 ORDER BY item_status='completed',due_at IS NULL,due_at,title LIMIT 80", (estate_id(),))
    try:
        metadata = json.loads(checkpoint.get("metadata") or "{}")
    except (TypeError, ValueError):
        metadata = {}
    error = checkpoint.get("last_error")
    work_plan = unified_work_plan()
    return {"calendar_entities": metadata.get("calendar_entities") or [], "todo_entities": metadata.get("todo_entities") or [], "events": json_ready(events), "items": json_ready(items), "work_items": work_plan["items"], "duplicates": work_plan["duplicates"], "apple_list": APPLE_LIST_NAME, "apple_treatments_list": APPLE_TREATMENTS_LIST_NAME, "calendar_connected": bool(checkpoint.get("last_success_at") and metadata.get("calendar_entities") and not error), "tasks_connected": bool(checkpoint.get("last_success_at") and metadata.get("todo_entities") and not error), "calendar_status": metadata.get("calendar_source") or "not synced", "tasks_status": metadata.get("todo_source") or "not synced", "last_sync_at": checkpoint.get("last_success_at"), "last_attempt_at": checkpoint.get("last_attempt_at"), "error": error}
