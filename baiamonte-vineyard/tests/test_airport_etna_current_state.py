from datetime import datetime, timedelta, timezone

from app.airport import _impact_assessment, _notice_operational_state
from app.etna import _activity_state, _annotate_ash_advisory


def _notice(hours_ago: int, title: str, summary: str) -> dict:
    return {
        "published_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
        "title": title,
        "summary": summary,
    }


def test_newer_reopening_supersedes_older_closure_notice():
    airport = {
        "official_notices": [
            _notice(1, "Etna eruption update", "Previously closed sectors have been reopened and all restrictions have been lifted. Flight operations have been restored."),
            _notice(3, "Etna eruption update", "Airspace sector B1 closed and arriving flights limited."),
        ],
        "metar": {"visibility_sm": 6, "raw": "METAR LICC 9999"},
    }
    result = _impact_assessment(airport, {"ash_advisory": {}})
    assert result["airspace_status"] == "normal"
    assert result["operational_notice_state"] == "resolved"
    assert result["level"] == "normal"


def test_reopening_language_is_not_misread_as_a_closure():
    assert _notice_operational_state("The closed sectors reopened and restrictions were lifted") == "resolved"


def test_final_vaac_advisory_is_concluded_not_current():
    result = _annotate_ash_advisory(
        {
            "issued_at": datetime.now(timezone.utc).strftime("%Y%m%d/%H%MZ"),
            "aviation_colour_code": "ORANGE",
            "no_ash_expected_12h": True,
            "next_advisory": "NO FURTHER ADVISORIES",
        },
        datetime.now(timezone.utc),
    )
    assert result["status"] == "concluded"
    assert result["current"] is False


def test_activity_chain_uses_latest_notice_even_when_rows_are_unsorted():
    rows = [
        {"sent_at": "2026-08-20T10:00:00Z", "description": "PRIMO COMUNICATO", "url": "start"},
        {"sent_at": "2026-08-20T12:00:00Z", "description": "FINE EVENTO", "url": "end"},
        {"sent_at": "2026-08-20T09:00:00Z", "description": "RIENTRO", "url": "old-end"},
    ]
    assert _activity_state(rows, datetime.now(timezone.utc))["active"] is False
