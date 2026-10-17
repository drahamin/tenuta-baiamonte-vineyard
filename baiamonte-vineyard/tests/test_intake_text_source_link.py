from pathlib import Path
from unittest.mock import MagicMock, patch

from starlette.requests import Request

from app.domains import alerts_intake_routes


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/intake/item/link",
        "headers": [(b"x-remote-user-name", b"David")],
    })


def test_text_only_intake_links_without_creating_a_file_attachment():
    cursor = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = (None, cursor)
    item = {
        "id": "item",
        "stored_path": None,
        "file_sha256": None,
        "message_text": "Excavator work by Nunzio",
    }
    with (
        patch.object(alerts_intake_routes, "fetch_one", side_effect=[item, {"id": "activity"}]),
        patch.object(alerts_intake_routes, "transaction", return_value=context),
        patch.object(alerts_intake_routes, "estate_id", return_value="estate"),
        patch.object(alerts_intake_routes, "audit") as audit,
    ):
        result = alerts_intake_routes.link_intake_to_record(
            "item", {"entity_type": "activity", "entity_id": "activity"}, _request()
        )

    assert result == {
        "saved": True,
        "attachment_id": None,
        "entity_id": "activity",
        "duplicate_link": False,
        "remaining_records": 0,
        "source_attached": False,
    }
    sql = cursor.execute.call_args.args[0]
    assert sql.startswith("UPDATE intake_items SET review_status='approved'")
    assert "INSERT INTO entity_attachments" not in sql
    audit.assert_called_once()
    assert audit.call_args.args[-1] == "David"


def test_text_only_intake_review_shows_text_instead_of_dead_file_buttons():
    source = (
        Path(__file__).resolve().parents[1] / "app/static/assets/intake-review.js"
    ).read_text(encoding="utf-8")

    assert "const hasFile=Boolean(item?.stored_path&&item?.original_filename)" in source
    assert "const sourceText=String(item?.message_text||item?.source_text||'').trim()" in source
    assert "${hasFile?`<a class=\"button-link\"" in source
    assert "there is no separate file to open or download" in source
