from app.sql_migrations import split_sql_statements


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
