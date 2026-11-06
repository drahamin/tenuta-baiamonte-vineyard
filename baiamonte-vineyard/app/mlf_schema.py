"""Fixed, read-only structural qualification; never inspect business rows."""
from typing import Any

_TEXT = ("utf8mb4", "utf8mb4_unicode_ci")
# Ordered name, type, nullable, MariaDB default, extra, charset, collation.
EXPECTED_MLF_COLUMNS = (
    ("id", "char(36)", "NO", None, "", *_TEXT),
    ("estate_id", "char(36)", "NO", None, "", *_TEXT),
    ("wine_lot_id", "char(36)", "NO", None, "", *_TEXT),
    ("product_name", "varchar(160)", "NO", "'LALVIN VP41 MBR'", "", *_TEXT),
    ("formulation", "varchar(40)", "NO", "'MBR'", "", *_TEXT),
    ("timing_plan", "varchar(40)", "NO", "'sequential'", "", *_TEXT),
    ("volume_min_l", "decimal(12,3)", "YES", "NULL", "", None, None),
    ("volume_max_l", "decimal(12,3)", "YES", "NULL", "", None, None),
    ("volume_basis", "varchar(40)", "NO", None, "", *_TEXT),
    ("volume_basis_note", "varchar(700)", "NO", None, "", *_TEXT),
    ("small_sachet_coverage_l", "decimal(12,3)", "NO", "250.000", "", None, None),
    ("large_sachet_coverage_l", "decimal(12,3)", "NO", "2500.000", "", None, None),
    ("exact_label_confirmed", "tinyint(1)", "NO", "0", "", None, None),
    ("suitability_confirmed", "tinyint(1)", "NO", "0", "", None, None),
    ("approved_by", "varchar(160)", "YES", "NULL", "", *_TEXT),
    ("notes", "text", "YES", "NULL", "", *_TEXT),
    ("updated_at", "datetime(6)", "NO", "current_timestamp(6)", "on update current_timestamp(6)", None, None),
)


def inspect_mlf_schema(cursor: Any, database: str) -> dict[str, bool]:
    """Require the exact schema, including indexes/FKs and absence of triggers.

    This attests structure only. It does not certify row provenance, estate
    attribution, approvals, or recovery of any business effects from 235.
    """
    cursor.execute(
        "SELECT column_name,column_type,is_nullable,column_default,extra,character_set_name,collation_name,ordinal_position "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name='enology_mlf_plans' ORDER BY ordinal_position",
        (database,),
    )
    columns = list(cursor.fetchall())
    keys = ("column_name", "column_type", "is_nullable", "column_default", "extra", "character_set_name", "collation_name")
    columns_ok = (
        [tuple(row.get(key) for key in keys) for row in columns] == list(EXPECTED_MLF_COLUMNS)
        and [row.get("ordinal_position") for row in columns] == list(range(1, len(EXPECTED_MLF_COLUMNS) + 1))
    )
    cursor.execute(
        "SELECT index_name,column_name,seq_in_index,non_unique,index_type,sub_part,ignored "
        "FROM information_schema.statistics WHERE table_schema=%s AND table_name='enology_mlf_plans' ORDER BY index_name,seq_in_index",
        (database,),
    )
    indexes = list(cursor.fetchall())
    actual_indexes = {(r["index_name"], r["column_name"], r["seq_in_index"], r["non_unique"], r["index_type"], r["sub_part"], r["ignored"]) for r in indexes}
    expected_indexes = {
        ("PRIMARY", "id", 1, 0, "BTREE", None, "NO"),
        ("uq_enology_mlf_plan_lot", "wine_lot_id", 1, 0, "BTREE", None, "NO"),
        ("fk_enology_mlf_plan_estate", "estate_id", 1, 1, "BTREE", None, "NO"),
    }
    cursor.execute(
        "SELECT k.constraint_name,k.column_name,k.referenced_table_schema,k.referenced_table_name,k.referenced_column_name,r.delete_rule,r.update_rule "
        "FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r "
        "ON r.constraint_schema=k.constraint_schema AND r.table_name=k.table_name AND r.constraint_name=k.constraint_name "
        "WHERE k.table_schema=%s AND k.table_name='enology_mlf_plans' AND k.referenced_table_name IS NOT NULL",
        (database,),
    )
    foreign_keys = list(cursor.fetchall())
    fk_keys = ("constraint_name", "column_name", "referenced_table_schema", "referenced_table_name", "referenced_column_name", "delete_rule", "update_rule")
    actual_fks = {tuple(r.get(key) for key in fk_keys) for r in foreign_keys}
    expected_fks = {
        ("fk_enology_mlf_plan_estate", "estate_id", database, "estates", "id", "RESTRICT", "RESTRICT"),
        ("fk_enology_mlf_plan_lot", "wine_lot_id", database, "wine_lots", "id", "CASCADE", "RESTRICT"),
    }
    cursor.execute(
        "SELECT engine,table_collation,table_type FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name='enology_mlf_plans'", (database,),
    )
    table = cursor.fetchone() or {}
    cursor.execute(
        "SELECT COUNT(*) n FROM information_schema.triggers WHERE trigger_schema=%s AND event_object_table='enology_mlf_plans'",
        (database,),
    )
    triggers = cursor.fetchone() or {}
    cursor.execute(
        "SELECT constraint_name,constraint_type FROM information_schema.table_constraints "
        "WHERE table_schema=%s AND table_name='enology_mlf_plans'", (database,),
    )
    constraints = list(cursor.fetchall())
    expected_constraints = {("PRIMARY", "PRIMARY KEY"), ("uq_enology_mlf_plan_lot", "UNIQUE"),
                            ("fk_enology_mlf_plan_estate", "FOREIGN KEY"), ("fk_enology_mlf_plan_lot", "FOREIGN KEY")}
    checks = {
        "columns_exact": columns_ok,
        "indexes_exact": len(indexes) == len(expected_indexes) and actual_indexes == expected_indexes,
        "foreign_keys_exact": len(foreign_keys) == len(expected_fks) and actual_fks == expected_fks,
        "table_exact": table.get("engine") == "InnoDB" and table.get("table_collation") == "utf8mb4_unicode_ci" and table.get("table_type") == "BASE TABLE",
        "no_triggers": triggers.get("n") == 0,
        "constraints_exact": len(constraints) == len(expected_constraints) and {(r.get("constraint_name"), r.get("constraint_type")) for r in constraints} == expected_constraints,
    }
    return {"ready": all(checks.values()), **checks}
