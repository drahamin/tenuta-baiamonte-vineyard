"""Compact reference options for attaching observations to existing work."""
from __future__ import annotations

from typing import Any

from ..db import fetch_all
from ..service import estate_id


def observation_chain_options(year: int) -> list[dict[str, Any]]:
    damage = fetch_all(
        "SELECT a.event_key,a.damage_type,MIN(a.event_date) first_date,COUNT(*) report_count "
        "FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id "
        "WHERE a.estate_id=%s AND s.vintage_year=%s AND a.active=1 AND a.event_key IS NOT NULL "
        "GROUP BY a.event_key,a.damage_type ORDER BY MAX(a.assessed_at) DESC",
        (estate_id(), year),
    )
    issues = fetch_all(
        "SELECT id,issue_type,issue_text FROM issues_decisions "
        "WHERE estate_id=%s AND status NOT IN ('resolved','closed','cancelled') ORDER BY opened_date DESC,id DESC LIMIT 100",
        (estate_id(),),
    )
    return [
        {"value": f"event:{row['event_key']}", "chain_type": "damage_event", "event_key": row["event_key"],
         "label": f"{str(row.get('damage_type') or 'Damage').replace('_', ' ').title()} · {row.get('first_date')} · {int(row.get('report_count') or 0)} reports"}
        for row in damage
    ] + [
        {"value": f"issue:{row['id']}", "chain_type": "issue", "issue_id": row["id"],
         "label": f"{row.get('issue_type') or 'Issue'} · {str(row.get('issue_text') or '')[:90]}"}
        for row in issues
    ]
