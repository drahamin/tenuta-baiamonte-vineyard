from unittest.mock import patch

from app.mcp_server import cellar_lab_references, lab_history


def test_history_exposes_exact_ids_with_estate_and_bound():
    rows = [{"sample_id": "sample-1", "wine_lot_id": "lot-1"}]
    with patch("app.mcp_server.estate_id", return_value="estate-1"), patch("app.mcp_server.fetch_all", return_value=rows) as read, patch("app.mcp_server.transaction") as write:
        assert lab_history(sample_name_contains="Sp", limit=999) == rows
    sql, params = read.call_args.args
    assert "s.id sample_id,s.wine_lot_id" in sql
    assert "s.estate_id=%s" in sql
    assert params == ("estate-1", "%Sp%", 250)
    write.assert_not_called()


def test_references_are_bounded_estate_scoped_and_read_only():
    rows = [{"id": str(i)} for i in range(3)]
    with patch("app.mcp_server.estate_id", return_value="estate-1"), patch("app.mcp_server.fetch_all", side_effect=[rows, rows[:1]]) as read, patch("app.mcp_server.transaction") as write:
        result = cellar_lab_references(limit=2)
    assert result == {"containers": rows[:2], "wine_lots": rows[:1], "containers_has_more": True, "wine_lots_has_more": False}
    for call in read.call_args_list:
        sql, params = call.args
        assert sql.startswith("SELECT ") and "WHERE estate_id=%s" in sql
        assert "ORDER BY code,id LIMIT %s" in sql
        assert params == ("estate-1", 3)
    write.assert_not_called()
