from app.sql_migrations import split_sql_statements
from pathlib import Path


def test_semicolons_inside_strings_do_not_split_migrations():
    statements = split_sql_statements(
        "INSERT INTO notes (body) VALUES ('Labor evidence only; payment not verified');"
        "UPDATE notes SET body='It''s confirmed; keep it';"
    )
    assert len(statements) == 2
    assert "payment not verified" in statements[0]
    assert "keep it" in statements[1]


def test_semicolons_inside_comments_do_not_split_migrations():
    source = "-- explanation; still one statement\nSELECT 1; /* follow-up; note */ SELECT 2;"
    statements = split_sql_statements(source)
    assert len(statements) == 2
    assert statements[0].endswith("SELECT 1")
    assert statements[1].endswith("SELECT 2")


def test_multi_service_startup_serializes_schema_migrations():
    source = (Path(__file__).resolve().parents[1] / "app" / "db.py").read_text(encoding="utf-8")
    assert "GET_LOCK(%s,60)" in source
    assert "baiamonte_schema_migrations" in source
    assert "RELEASE_LOCK(%s)" in source
    assert source.index("GET_LOCK(%s,60)") < source.index("SELECT version FROM schema_migrations")
    assert "Database migration failed:" in source
    assert "statement_number" in source
