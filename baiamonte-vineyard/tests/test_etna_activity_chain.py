from datetime import datetime, timezone

from app.etna import _activity_state, _communications


def test_busy_event_keeps_opening_notice_beyond_twenty_updates():
    updates = "".join(
        f"<tr><td>2026-08-{21 - index // 3:02d} 18:{index:02d}:00</td>"
        "<td>INVIO COMUNICATO GENERICO DI ATTIVIT&Agrave; VULCANICA</td>"
        "<td>ETNA</td><td><a href='/update.pdf'>PDF</a></td></tr>"
        for index in range(21)
    )
    opening = (
        "<tr><td>2026-08-08 09:32:00</td>"
        "<td>PRIMO COMUNICATO DI NOTIFICA EVENTO</td>"
        "<td>ETNA</td><td><a href='/opening.pdf'>PDF</a></td></tr>"
    )
    rows = _communications(updates + opening)
    state = _activity_state(rows, datetime(2026, 8, 22, tzinfo=timezone.utc))

    assert len(rows) == 22
    assert state["active"] is True
    assert state["since"] == "2026-08-08T09:32:00Z"
    assert state["source"]["sent_at"] == "2026-08-21T18:02:00Z"
    assert state["opening_notice"]["url"].endswith("/opening.pdf")


def test_explicit_close_remains_authoritative_after_many_updates():
    rows = [
        {"sent_at": "2026-08-22T08:00:00Z", "description": "FINE EVENTO", "url": "close"},
        {"sent_at": "2026-08-21T18:00:00Z", "description": "INVIO COMUNICATO GENERICO DI ATTIVITÀ VULCANICA", "url": "update"},
        {"sent_at": "2026-08-08T09:32:00Z", "description": "PRIMO COMUNICATO DI NOTIFICA EVENTO", "url": "open"},
    ]

    state = _activity_state(rows, datetime(2026, 8, 22, tzinfo=timezone.utc))

    assert state["active"] is False
    assert state["source"]["url"] == "close"
    assert state["closing_notice"]["url"] == "close"
