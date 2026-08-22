"""Explicit, auditable pre/post scouting pairs for treatment learning."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..service import estate_id, json_ready, new_id


TARGET_ISSUES = {
    "downy_mildew": {"downy_mildew"},
    "powdery_mildew": {"powdery_mildew"},
    "botrytis": {"botrytis_grey_mold", "other_mold_rot", "hail_mold_rot"},
}


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _targets(application_id: str) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT DISTINCT u.target_code,u.target_name FROM spray_application_items i "
        "JOIN product_authorized_uses u ON u.product_id=i.product_id AND u.crop_scope='vineyard' AND u.active=1 "
        "WHERE i.application_id=%s ORDER BY u.target_name,u.target_code",
        (application_id,),
    )
    if rows:
        return rows
    learned = fetch_one(
        "SELECT objectives_snapshot FROM treatment_weather_learning_cases WHERE estate_id=%s AND application_id=%s",
        (estate_id(), application_id),
    ) or {}
    objectives = learned.get("objectives_snapshot")
    if isinstance(objectives, str):
        try:
            objectives = json.loads(objectives)
        except (TypeError, ValueError):
            objectives = []
    if isinstance(objectives, list) and objectives:
        return [{"target_code": row.get("target_code"), "target_name": row.get("target_name")} for row in objectives if row.get("target_code")]
    application = fetch_one("SELECT purpose FROM spray_applications WHERE id=%s AND estate_id=%s", (application_id, estate_id())) or {}
    purpose = str(application.get("purpose") or "").casefold()
    fallbacks = (("downy_mildew", "Downy mildew", ("downy", "peronospora")),
                 ("powdery_mildew", "Powdery mildew", ("powdery", "oidium", "oidio")),
                 ("botrytis", "Botrytis / grey mold", ("botrytis", "grey mold", "gray mold", "muffa")))
    return [{"target_code": code, "target_name": name} for code, name, terms in fallbacks if any(term in purpose for term in terms)]


def linked_scouting(application_id: str, phase: str) -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT s.issue_type,s.severity,s.incidence_pct,s.notes,s.observed_at,l.target_code,l.link_method "
        "FROM treatment_scouting_links l JOIN scouting_observations s ON s.id=l.observation_id "
        "WHERE l.estate_id=%s AND l.application_id=%s AND l.phase=%s ORDER BY s.observed_at",
        (estate_id(), application_id, phase),
    )


def has_explicit_pairing(application_id: str) -> bool:
    row = fetch_one(
        "SELECT COUNT(*) count FROM treatment_scouting_links WHERE estate_id=%s AND application_id=%s",
        (estate_id(), application_id),
    ) or {}
    return bool(row.get("count"))


def validate_observation_pair(values: dict[str, Any]) -> dict[str, Any] | None:
    application_id = str(values.get("treatment_application_id") or "").strip()
    phase = str(values.get("treatment_observation_phase") or "").strip().casefold()
    target_code = str(values.get("treatment_target_code") or "").strip().casefold() or None
    if not application_id and not phase and not target_code:
        return None
    if not application_id or phase not in {"pre", "post"}:
        raise ValueError("Choose a treatment and whether this is the before or after observation")
    application = fetch_one(
        "SELECT id,DATE(application_date) application_date,block_id,crop_scope,status,purpose FROM spray_applications "
        "WHERE id=%s AND estate_id=%s",
        (application_id, estate_id()),
    )
    if not application or application.get("crop_scope") != "vineyard":
        raise ValueError("Choose a vineyard treatment")
    observed_on = _day(values.get("observed_at"))
    applied_on = _day(application.get("application_date"))
    if not observed_on or not applied_on:
        raise ValueError("The observation and treatment dates are required")
    start, end = ((applied_on - timedelta(days=14), applied_on) if phase == "pre" else (applied_on + timedelta(days=1), applied_on + timedelta(days=14)))
    if not start <= observed_on <= end:
        label = "14 days before through treatment day" if phase == "pre" else "1–14 days after treatment"
        raise ValueError(f"This paired observation must be recorded within {label}")
    if application.get("block_id") and values.get("block_id") != application.get("block_id"):
        raise ValueError("The paired observation must use the treatment's vineyard block")
    targets = _targets(application_id)
    target_codes = {str(row.get("target_code") or "").casefold() for row in targets}
    if target_codes and target_code not in target_codes:
        raise ValueError("Choose one of the treatment's recorded disease targets")
    allowed_issues = TARGET_ISSUES.get(target_code or "", set())
    issue = str(values.get("issue_type") or "").casefold()
    if allowed_issues and issue not in allowed_issues:
        raise ValueError("The field observation must match the selected treatment target")
    return {"application_id": application_id, "phase": phase, "target_code": target_code}


def link_observation(values: dict[str, Any], observation_id: str, linked_by: str = "home-assistant") -> dict[str, Any] | None:
    pairing = validate_observation_pair(values)
    if not pairing:
        return None
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO treatment_scouting_links (id,estate_id,application_id,observation_id,phase,target_code,link_method,linked_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,'explicit',%s)",
            (new_id(), estate_id(), pairing["application_id"], observation_id, pairing["phase"], pairing["target_code"], linked_by),
        )
    return pairing


def auto_link_observation(values: dict[str, Any], observation_id: str, linked_by: str = "observation-router") -> dict[str, Any] | None:
    """Link only an unambiguous block/date/target match; never guess between treatments."""
    observed_on = _day(values.get("observed_at"))
    block_id = values.get("block_id")
    issue = str(values.get("issue_type") or "").casefold()
    if not observed_on or not block_id or not issue:
        return None
    applications = fetch_all(
        "SELECT id,DATE(application_date) application_date FROM spray_applications WHERE estate_id=%s AND crop_scope='vineyard' "
        "AND block_id=%s AND status IN ('planned','completed','applied') AND DATE(application_date) BETWEEN %s AND %s",
        (estate_id(), block_id, observed_on - timedelta(days=14), observed_on + timedelta(days=14)),
    )
    matches: list[dict[str, Any]] = []
    for application in applications:
        applied_on = _day(application.get("application_date"))
        if not applied_on:
            continue
        phase = "pre" if applied_on - timedelta(days=14) <= observed_on <= applied_on else "post" if applied_on + timedelta(days=1) <= observed_on <= applied_on + timedelta(days=14) else None
        if not phase:
            continue
        for target in _targets(application["id"]):
            code = str(target.get("target_code") or "").casefold()
            if issue in TARGET_ISSUES.get(code, set()):
                matches.append({"application_id": application["id"], "phase": phase, "target_code": code})
    unique = {(item["application_id"], item["phase"], item["target_code"]): item for item in matches}
    if len(unique) != 1:
        return None
    pairing = next(iter(unique.values()))
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT IGNORE INTO treatment_scouting_links (id,estate_id,application_id,observation_id,phase,target_code,link_method,linked_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,'automatic',%s)",
            (new_id(), estate_id(), pairing["application_id"], observation_id, pairing["phase"], pairing["target_code"], linked_by),
        )
    return pairing


def treatment_scouting_workflows(year: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT a.id,a.application_date,a.purpose,a.status,a.block_id,b.code block_code,o.outcome_status,o.effectiveness_label,o.outcome_summary "
        "FROM spray_applications a LEFT JOIN vineyard_blocks b ON b.id=a.block_id "
        "LEFT JOIN treatment_learning_outcomes o ON o.application_id=a.id AND o.estate_id=a.estate_id "
        "WHERE a.estate_id=%s AND a.crop_scope='vineyard' AND YEAR(a.application_date)=%s "
        "AND a.status IN ('planned','completed','applied') ORDER BY a.application_date DESC",
        (estate_id(), year),
    )
    today = date.today()
    result = []
    for row in rows:
        applied_on = _day(row.get("application_date"))
        if not applied_on:
            continue
        targets = _targets(row["id"])
        if not targets:
            continue
        links = fetch_all(
            "SELECT l.phase,l.target_code,s.id observation_id,s.observed_at,s.issue_type,s.severity,s.incidence_pct "
            "FROM treatment_scouting_links l JOIN scouting_observations s ON s.id=l.observation_id "
            "WHERE l.estate_id=%s AND l.application_id=%s ORDER BY s.observed_at",
            (estate_id(), row["id"]),
        )
        pre = [item for item in links if item.get("phase") == "pre"]
        post = [item for item in links if item.get("phase") == "post"]
        if not pre:
            workflow_status, next_phase = ("baseline_needed" if today <= applied_on else "baseline_missing"), "pre"
        elif row.get("status") == "planned" or today < applied_on + timedelta(days=1):
            workflow_status, next_phase = "baseline_recorded", None
        elif not post and today <= applied_on + timedelta(days=14):
            workflow_status, next_phase = "followup_due", "post"
        elif not post:
            workflow_status, next_phase = "followup_overdue", "post"
        else:
            workflow_status, next_phase = "complete", None
        result.append({
            **row, "application_date": applied_on, "targets": targets, "pre_observations": pre,
            "post_observations": post, "pre_count": len(pre), "post_count": len(post),
            "workflow_status": workflow_status, "next_phase": next_phase,
            "pre_window_start": applied_on - timedelta(days=14), "pre_window_end": applied_on,
            "post_window_start": applied_on + timedelta(days=1), "post_window_end": applied_on + timedelta(days=14),
        })
    return json_ready(result)
