from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any


def consolidate_labor_people(
    people: list[dict[str, Any]], canonical_keys: set[str]
) -> list[dict[str, Any]]:
    """Merge seeded workers with authoritative Home Assistant people."""
    normalized_canonical_keys = sorted(
        ((re.sub(r"\W+", "_", str(key).casefold()).strip("_"), key) for key in canonical_keys),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    consolidated: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for person in people:
        raw_key = re.sub(r"\W+", "_", str(person.get("key") or "").casefold()).strip("_")
        identity = next(
            (canonical_key for normalized_key, canonical_key in normalized_canonical_keys
             if raw_key == normalized_key or raw_key.startswith(f"{normalized_key}_")),
            re.sub(r"\W+", " ", str(person.get("name") or raw_key).casefold()).strip(),
        )
        existing = consolidated.get(identity)
        if not existing:
            consolidated[identity] = dict(person)
            ordered_keys.append(identity)
            continue
        if person.get("person_entity"):
            existing["name"] = person.get("name") or existing.get("name")
            existing["person_entity"] = person["person_entity"]
            if person.get("gps_entity"):
                existing["gps_entity"] = person["gps_entity"]
        for field in ("role", "payment_schedule"):
            if person.get(field) and not existing.get(field):
                existing[field] = person[field]
        existing["name_aliases"] = tuple(dict.fromkeys((*existing.get("name_aliases", ()), *person.get("name_aliases", ()))))
        existing["camera_aliases"] = tuple(dict.fromkeys((*existing.get("camera_aliases", ()), *person.get("camera_aliases", ()))))
    return [consolidated[key] for key in ordered_keys]


def worker_pay_due(name: str, work_day: date) -> date | None:
    if "giancarlo" not in name.casefold():
        return None
    next_month = (work_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month.replace(day=15)


def worker_payment_batch_key(row: dict[str, Any]) -> str:
    """Keep records from one reviewed source together through payment."""
    source_id = str(row.get("source_labor_id") or "")
    timesheet_match = re.match(r"^TIMESHEET-([^-]+)-", source_id, re.IGNORECASE)
    if timesheet_match:
        return f"timesheet:{timesheet_match.group(1).casefold()}"
    expense_match = re.match(r"^([^:]+):expense:\d+$", source_id, re.IGNORECASE)
    if expense_match:
        return f"timesheet:{expense_match.group(1)[:8].casefold()}"
    notes_match = re.search(r"timesheet\s+([0-9a-f-]{8,36})", str(row.get("notes") or ""), re.IGNORECASE)
    if notes_match:
        return f"timesheet:{notes_match.group(1)[:8].casefold()}"
    worker = re.sub(
        r"[^a-z0-9]+", "-",
        str(row.get("person_or_crew") or row.get("worker_username") or "worker").casefold(),
    ).strip("-") or "worker"
    work_month = str(row.get("work_date") or "")[:7]
    if re.fullmatch(r"\d{4}-\d{2}", work_month):
        return f"period:{worker}:{work_month}"
    return f"record:{row.get('id')}"


def normalize_contractor_job_lines(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate fixed-price contractor lines and map them to one payable record."""
    lines = payload.get("job_lines")
    if not isinstance(lines, list) or not lines or len(lines) > 50:
        raise ValueError("Add between 1 and 50 contractor job lines")
    cleaned: list[dict[str, Any]] = []
    dates: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Each contractor job must be a line item")
        description = str(line.get("description") or "").strip()
        if not description:
            raise ValueError("Each contractor job needs a description")
        try:
            amount = round(float(line.get("amount_eur") or 0), 2)
        except (TypeError, ValueError) as error:
            raise ValueError("Each contractor job needs a valid amount") from error
        if amount <= 0 or amount > 100000:
            raise ValueError("Contractor job amounts must be between €0.01 and €100,000")
        line_date = str(line.get("date") or "").strip()
        if line_date:
            try:
                line_date = date.fromisoformat(line_date).isoformat()
            except ValueError as error:
                raise ValueError("Use a valid date on each dated contractor job") from error
            dates.append(line_date)
        cleaned.append({"date": line_date or None, "description": description[:500], "amount_eur": amount})
    total = round(sum(line["amount_eur"] for line in cleaned), 2)
    note = str(payload.get("notes") or "").strip()
    return {
        "work_date": max(dates) if dates else date.today().isoformat(),
        "regular_hours": 0, "overtime_hours": 0, "hourly_rate_eur": None,
        "labor_cost_eur": 0, "other_cost_eur": total, "expense_amount_eur": total,
        "expense_category": "contractor_job",
        "expense_notes": json.dumps({"version": 1, "kind": "contractor_job_lines", "job_lines": cleaned, "note": note or None}, ensure_ascii=False),
        "work_category": "one_off_charge", "entry_source": "manual_job", "payroll_scope": "contractor",
        "work_performed": str(payload.get("work_performed") or "Contractor services").strip()[:500],
    }
