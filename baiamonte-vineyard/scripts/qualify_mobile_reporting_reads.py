#!/usr/bin/env python3
"""One-shot local-runtime qualification; no listener, credentials output or DML.

Run only through an already-authorized Vineyard runtime execution path.
This script must not be used to bypass denied SSH/database access.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


REVIEWED_MODULE_SHA256 = "406d3f77996891bc0523955eb8cdd6923a915e542a4a8c615f83691d633d8d48"
REQUIRED = {
    "estates": "id name",
    "grape_varieties": "id estate_id name active",
    "cellar_containers": "id estate_id code name capacity_l status active",
    "wine_lots": "id estate_id season_id current_container_id stage volume_l",
    "seasons": "id estate_id vintage_year",
    "tasks": "id estate_id title category status priority due_date updated_at block_id",
    "vineyard_blocks": "id estate_id code",
    "alerts": "id estate_id alert_type severity title message status triggered_at resolved_at",
    "issues_decisions": "id estate_id issue_text issue_type priority status due_date subject_ref decision_action opened_date",
    "ro_lab_decision_queue": "estate_id sample_type flagged_results review_status lab_date",
    "harvest_plans": "estate_id season_id variety_id planned_kg",
    "harvest_lots": "estate_id season_id variety_id weight_kg source_type harvested_at",
}


class QualificationFailure(RuntimeError):
    pass


def validate_runtime(settings: Any) -> None:
    # Do not fall back to blank/default credentials or another database. The
    # operator must already have the approved initialized app environment;
    # this tool does not extract options, /proc environments or secrets.
    if settings.db_name != "baiamonte_vineyard" or not settings.db_password:
        raise QualificationFailure("approved initialized Vineyard environment required")


def qualify(module: Any, connection: Any, estate: str, year: int, *, clock=time.monotonic) -> dict[str, Any]:
    """Use one read-only snapshot; emit aggregate counts/timings, never rows."""
    allowed = set(REQUIRED) | {"information_schema.columns"}
    original_all, original_one = module.fetch_all, module.fetch_one
    result: dict[str, Any] = {"schema_ready": False, "reads": [], "application_cache": "unused", "database_cache_flushed": False}
    count = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION max_statement_time=2")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            tables = sorted(REQUIRED)
            cursor.execute(
                "SELECT table_name,column_name FROM information_schema.columns "
                "WHERE table_schema=DATABASE() AND table_name IN (" + ",".join(["%s"] * len(tables)) + ") LIMIT 1000",
                tuple(tables),
            )
            columns: dict[str, set[str]] = {table: set() for table in tables}
            for row in cursor.fetchall():
                if row["table_name"] not in columns:
                    raise QualificationFailure("schema scope mismatch")
                columns[row["table_name"]].add(row["column_name"])
            missing = {table: sorted(set(fields.split()) - columns[table]) for table, fields in REQUIRED.items()}
            missing = {table: fields for table, fields in missing.items() if fields}
            if not ({"id", "sample_id"} & columns["ro_lab_decision_queue"]):
                missing["ro_lab_decision_queue"] = [*missing.get("ro_lab_decision_queue", []), "id_or_sample_id"]
            if missing:
                # Column/table names only; no data, credentials or SQL parameters.
                return {**result, "missing_columns": missing}
            result["schema_ready"] = True

            def query(sql, params, *, one=False):
                nonlocal count
                sources = set(re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql, re.IGNORECASE))
                if not sql.startswith("SELECT ") or not sources or not sources <= allowed or ";" in sql:
                    raise QualificationFailure("query is not an approved reporting SELECT")
                cursor.execute(sql, params)
                count += 1
                return cursor.fetchone() if one else list(cursor.fetchall())

            module.fetch_all = lambda sql, params: query(sql, params)
            module.fetch_one = lambda sql, params: query(sql, params, one=True)

            def measure(label, action, max_queries):
                before_count, started = count, clock()
                data = action()
                elapsed = clock() - started
                queries = count - before_count
                if elapsed >= 5 or queries > max_queries:
                    raise QualificationFailure("read exceeded qualification budget")
                if isinstance(data, list):
                    if len(data) > 100:
                        raise QualificationFailure("unbounded records")
                    row_count = len(data)
                else:
                    row_count = {key: len(value) for key, value in data.items() if isinstance(value, list)}
                    if any(value > 100 for value in row_count.values()):
                        raise QualificationFailure("unbounded reporting section")
                result["reads"].append({"read": label, "seconds": round(elapsed, 6), "queries": queries, "row_count": row_count})

            measure("cold_catalog", lambda: module.read_catalog(estate, year), 3)
            for kind in ("tasks", "alerts", "issues", "labs", "cellar", "grapes"):
                measure("next_records_" + kind, lambda kind=kind: module.read_records(kind, estate, year, 100), 2)
            measure("work", lambda: module.read_records("tasks", estate, year, 100), 1)
            measure("review", lambda: {
                "alerts": module.read_records("alerts", estate, year, 100),
                "issues": module.read_records("issues", estate, year, 100),
                "labs": module.read_records("labs", estate, year, 100),
            }, 4)
            result["ok"] = True
            return result
    finally:
        module.fetch_all, module.fetch_one = original_all, original_one
        connection.rollback()  # Never commit even a successful qualification.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True, help="Private staged copy of the reviewed module")
    args = parser.parse_args()
    module_path = args.module.resolve(strict=True)
    if hashlib.sha256(module_path.read_bytes()).hexdigest() != REVIEWED_MODULE_SHA256:
        raise QualificationFailure("candidate hash mismatch")
    sys.path.insert(0, "/opt/baiamonte")
    # Existing on-host runtime configuration only. Never print/copy its secrets.
    from app.db import connect
    from app.config import get_settings
    from app.service import estate_id
    from app.estate_time import estate_year
    validate_runtime(get_settings())
    spec = importlib.util.spec_from_file_location("app.domains._mobile_reporting_candidate", module_path)
    if spec is None or spec.loader is None:
        raise QualificationFailure("candidate unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection = connect()
    try:
        result = qualify(module, connection, estate_id(), estate_year())
    finally:
        connection.close()
    print(json.dumps(result, sort_keys=True))
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = error.args[0] if error.args and isinstance(error.args[0], int) else None
        print(json.dumps({"ok": False, "error_type": type(error).__name__, "database_error_code": code}))
        raise SystemExit(2) from None
