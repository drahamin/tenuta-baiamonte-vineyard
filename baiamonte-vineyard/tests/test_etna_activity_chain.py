from datetime import datetime, timezone

from app.etna import _activity_state, _communications, _regional_etna_notices, _vona_notices


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


def test_newer_green_vona_resolves_an_unclosed_activity_notice():
    rows = [{"sent_at": "2026-10-12T02:03:57Z", "description": "PRIMO COMUNICATO", "url": "opening"}]
    vona = {
        "issued_at": "2026-10-16T12:27:58Z",
        "aviation_colour_code": "GREEN",
        "description": "Aviation Color Code: GREEN",
        "url": "final-vona",
    }

    state = _activity_state(rows, datetime(2026, 10, 26, tzinfo=timezone.utc), vona)

    assert state["active"] is False
    assert state["alerting"] is False
    assert state["aviation_colour_code"] == "GREEN"
    assert state["source"]["url"] == "final-vona"


def test_vona_and_regional_notice_parsers_keep_latest_authority():
    vona_html = """
    <tr><td>ETNA</td><td>2026-10-03 06:29:23</td><td>Aviation Color Code: YELLOW</td><td><a href='/yellow.pdf'>PDF</a></td></tr>
    <tr><td>ETNA</td><td>2026-10-16 12:27:58</td><td>Aviation Color Code: GREEN</td><td><a href='/green.pdf'>PDF</a></td></tr>
    """
    regional_html = """
    <a href='/AVVISO%20ETNAS%20F1%2012.10.2026%20ALLARME.pdf' title='AVVISO REGIONALE DI PROTEZIONE CIVILE PER EVENTI VULCANICI ETNA - 01 DEL 12.10.2026'>one</a>
    <a href='/AVVISO%20ETNAS%20F0%2012.10.2026%20PREALLARME.pdf' title='AVVISO REGIONALE DI PROTEZIONE CIVILE PER EVENTI VULCANICI ETNA - 02 DEL 12.10.2026'>two</a>
    """

    vona = _vona_notices(vona_html)
    regional = _regional_etna_notices(regional_html)

    assert vona[0]["aviation_colour_code"] == "GREEN"
    assert regional[0]["notice_number"] == "02"
    assert regional[0]["phase"] == "preallarme"
    assert regional[0]["etnas_level"] == "F0"
