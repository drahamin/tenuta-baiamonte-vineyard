from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.mcp_server import intake_review_detail


ITEM_ID = "07f8a879-bf53-43a4-aaba-1317e4429c52"


def test_existing_detail_is_returned_without_mutation():
    evidence = {"id": ITEM_ID, "source": "whatsapp", "external_id": "platform-id",
                "message_text": "source text", "review_status": "ready_for_review"}
    with patch("app.domains.alerts_intake_routes.intake_detail", return_value=evidence) as read:
        assert intake_review_detail(ITEM_ID) == evidence
        read.assert_called_once_with(ITEM_ID)


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", "' OR 1=1 --"])
def test_invalid_ids_are_rejected_before_read(bad_id):
    with patch("app.domains.alerts_intake_routes.intake_detail") as read:
        with pytest.raises(ValueError, match="exact intake item UUID"):
            intake_review_detail(bad_id)
        read.assert_not_called()


def test_missing_or_other_estate_item_is_not_found():
    with patch("app.domains.alerts_intake_routes.intake_detail", side_effect=HTTPException(404)):
        with pytest.raises(ValueError, match="not found in this estate"):
            intake_review_detail(ITEM_ID)


def test_detail_uses_estate_scoped_select_and_excludes_internal_path():
    row = {"id": ITEM_ID, "source": "whatsapp", "external_id": "message-id",
           "stored_path": "/private/source", "file_sha256": None, "extracted_data": None}
    with patch("app.domains.alerts_intake_routes.estate_id", return_value="estate-1"), \
         patch("app.domains.alerts_intake_routes.fetch_one", return_value=row) as select, \
         patch("app.domains.alerts_intake_routes.fetch_all", return_value=[]), \
         patch("app.domains.alerts_intake_routes.transaction") as transaction:
        result = intake_review_detail(ITEM_ID)
    sql, params = select.call_args.args
    assert "id=%s AND estate_id=%s" in sql
    assert params == (ITEM_ID, "estate-1")
    assert "stored_path" not in result
    transaction.assert_not_called()
