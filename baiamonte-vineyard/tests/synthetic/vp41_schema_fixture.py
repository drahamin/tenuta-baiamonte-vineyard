"""Run manually inside an offline container with a synthetic MariaDB socket.

Never invokes startup/lifespan or connects over TCP. Fixture names are fixed;
all records are invented. Root has an empty password only in this disposable
server, which must be started with --network none and --skip-networking.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pymysql
from app import db
from app.migration_policy import MLF_SCHEMA_MIGRATION, RETIRED_MLF_MIGRATION
from app.mlf_schema import inspect_mlf_schema
from app.sql_migrations import split_sql_statements

SOCKET = "/run/mysqld/mysqld.sock"
PREFIX = "vp41_synthetic_"
RESULTS = []
ROOT = Path(__file__).resolve().parents[2]


def connection(database=None):
    assert database is None or database.startswith(PREFIX)
    return pymysql.connect(unix_socket=SOCKET, user="root", password="", database=database,
                           charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def setup(case, *, table=True, legacy_ledger=False, successor_ledger=False, incompatible=False):
    name = PREFIX + case
    assert name.replace("_", "").isalnum()
    c = connection()
    with c.cursor() as q:
        q.execute(f"DROP DATABASE IF EXISTS `{name}`")
        q.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    c.close()
    c = connection(name)
    with c.cursor() as q:
        for sql in (
            "CREATE TABLE estates (id CHAR(36) PRIMARY KEY) ENGINE=InnoDB",
            "CREATE TABLE wine_lots (id CHAR(36) PRIMARY KEY, estate_id CHAR(36), code VARCHAR(40)) ENGINE=InnoDB",
            "CREATE TABLE enology_recipe_preferences (id CHAR(36) PRIMARY KEY,estate_id CHAR(36),mlf_intent VARCHAR(40),updated_by VARCHAR(100)) ENGINE=InnoDB",
            "CREATE TABLE enology_product_catalog (id CHAR(36) PRIMARY KEY,manufacturer VARCHAR(100),normalized_name VARCHAR(160),notes TEXT) ENGINE=InnoDB",
            "CREATE TABLE enology_product_protocols (id CHAR(36) PRIMARY KEY,product_catalog_id CHAR(36),required_lab_analytes TEXT,notes TEXT) ENGINE=InnoDB",
            "CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY,applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)) ENGINE=InnoDB",
            "INSERT INTO estates VALUES ('estate-a'),('estate-b')",
            "INSERT INTO wine_lots VALUES ('lot-a','estate-a','NM-2026-01'),('lot-b','estate-b','NM-2026-01')",
            "INSERT INTO enology_recipe_preferences VALUES ('pref-a','estate-a','block','human'),('pref-b','estate-b','block','other-human')",
            "INSERT INTO enology_product_catalog VALUES ('cat-a','LALLEMAND OENOLOGY','lalvin vp41','custom-old'),('cat-b','LALLEMAND OENOLOGY','lalvin vp41 mbr','custom-new')",
            "INSERT INTO enology_product_protocols VALUES ('protocol-a','cat-a','ph','keep-protocol-a'),('protocol-b','cat-b','total_so2','keep-protocol-b')",
        ):
            q.execute(sql)
        if table:
            for sql in split_sql_statements((ROOT / "db/migrations" / MLF_SCHEMA_MIGRATION).read_text()):
                q.execute(sql)
            q.execute("INSERT INTO enology_mlf_plans (id,estate_id,wine_lot_id,volume_min_l,volume_max_l,volume_basis,volume_basis_note,small_sachet_coverage_l,large_sachet_coverage_l,exact_label_confirmed,suitability_confirmed,approved_by,notes) VALUES ('plan-a','estate-a','lot-a',635,635,'measured_current','human-measured provenance',200,2000,1,1,'fixture-enologist','preserve approvals and note'),('plan-b','estate-b','lot-b',123,125,'measured_current','other-estate provenance',100,1000,0,0,NULL,'other estate')")
        if incompatible:
            q.execute("ALTER TABLE enology_mlf_plans MODIFY COLUMN product_name VARCHAR(160) NOT NULL DEFAULT 'unsafe-default'")
        for value, enabled in ((RETIRED_MLF_MIGRATION, legacy_ledger), (MLF_SCHEMA_MIGRATION, successor_ledger)):
            if enabled:
                q.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (value,))
    c.commit()
    c.close()
    db.connect = lambda: connection(name)
    db.get_settings = lambda: SimpleNamespace(db_name=name)
    os.environ["BAIAMONTE_MIGRATION_ALLOWLIST"] = MLF_SCHEMA_MIGRATION
    return name


def snapshot(name, include_plan=True):
    tables = ["estates", "wine_lots", "enology_recipe_preferences", "enology_product_catalog", "enology_product_protocols"]
    if include_plan:
        tables.append("enology_mlf_plans")
    c = connection(name)
    with c.cursor() as q:
        value = {}
        for table in tables:
            q.execute(f"SELECT * FROM `{table}` ORDER BY id")
            value[table] = q.fetchall()
    c.close()
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True).encode()).hexdigest()


def ledger(name):
    c = connection(name)
    with c.cursor() as q:
        q.execute("SELECT version FROM schema_migrations ORDER BY version")
        rows = [r["version"] for r in q.fetchall()]
    c.close()
    return rows


def run():
    c = connection()
    with c.cursor() as q:
        q.execute("SELECT VERSION() version,@@skip_networking no_tcp")
        server = q.fetchone()
        assert server["no_tcp"] == 1
    c.close()
    for case, legacy in (("absent", False), ("applied", True), ("partial_business", False), ("applied_missing_table", True)):
        has_plan = case not in {"absent", "applied_missing_table"}
        name = setup(case, table=has_plan, legacy_ledger=legacy)
        before = snapshot(name, has_plan)
        assert db.run_migrations() == [MLF_SCHEMA_MIGRATION]
        assert before == snapshot(name, has_plan)
        if not has_plan:
            c = connection(name)
            with c.cursor() as q:
                q.execute("SELECT COUNT(*) n FROM enology_mlf_plans")
                assert q.fetchone()["n"] == 0
            c.close()
        assert ledger(name) == sorted(([RETIRED_MLF_MIGRATION] if legacy else []) + [MLF_SCHEMA_MIGRATION])
        after = snapshot(name)
        assert db.run_migrations() == []
        assert snapshot(name) == after
        RESULTS.append({"case": case, "business_before_sha256": before, "business_after_sha256": snapshot(name, has_plan), "retry_unchanged": True})
    for recorded in (False, True):
        name = setup("incompatible_" + str(int(recorded)), incompatible=True, successor_ledger=recorded)
        before, old_ledger = snapshot(name), ledger(name)
        try:
            db.run_migrations()
            raise AssertionError("incompatible schema accepted")
        except RuntimeError:
            pass
        assert snapshot(name) == before and ledger(name) == old_ledger
        RESULTS.append({"case": "incompatible_with_ledger" if recorded else "incompatible_without_ledger", "blocked": True, "unchanged": True})
    name = setup("partial_ddl", table=False)
    before = snapshot(name, False)
    original = db.inspect_mlf_schema
    db.inspect_mlf_schema = lambda *_: {"ready": False}
    try:
        try:
            db.run_migrations()
            raise AssertionError("failed postcondition accepted")
        except RuntimeError:
            pass
    finally:
        db.inspect_mlf_schema = original
    assert ledger(name) == [] and snapshot(name, False) == before
    c = connection(name)
    with c.cursor() as q:
        assert inspect_mlf_schema(q, name)["ready"] is True  # DDL survived rollback.
    c.close()
    assert db.run_migrations() == [MLF_SCHEMA_MIGRATION]
    assert snapshot(name, False) == before
    RESULTS.append({"case": "partial_ddl_retry", "ddl_survived_rollback": True, "no_false_ledger": True, "retry_passed": True})
    name = setup("ledger_failure", table=False)
    before = snapshot(name, False)
    class FaultCursor:
        def __init__(self, cursor):
            self.cursor = cursor
        def __enter__(self):
            self.cursor.__enter__()
            return self
        def __exit__(self, *args):
            return self.cursor.__exit__(*args)
        def __getattr__(self, key):
            return getattr(self.cursor, key)
        def execute(self, query, params=None):
            result = self.cursor.execute(query, params)
            if query.startswith("INSERT INTO schema_migrations"):
                raise RuntimeError("synthetic failure after ledger INSERT before COMMIT")
            return result
    class FaultConnection:
        def __init__(self):
            self.connection = connection(name)
        def cursor(self):
            return FaultCursor(self.connection.cursor())
        def __getattr__(self, key):
            return getattr(self.connection, key)
    db.connect = FaultConnection
    try:
        db.run_migrations()
        raise AssertionError("fault injection did not run")
    except RuntimeError as error:
        assert "synthetic failure" in str(error)
    assert ledger(name) == [] and before == snapshot(name, False)
    db.connect = lambda: connection(name)
    assert db.run_migrations() == [MLF_SCHEMA_MIGRATION]
    assert before == snapshot(name, False)
    RESULTS.append({"case": "ledger_insert_failure_retry", "ledger_insert_rolled_back": True, "ddl_persisted": True, "business_unchanged": True, "retry_passed": True})
    name = setup("trigger")
    c = connection(name)
    with c.cursor() as q:
        q.execute("CREATE TRIGGER unexpected_mlf BEFORE UPDATE ON enology_mlf_plans FOR EACH ROW SET NEW.notes='unexpected'")
    c.commit()
    c.close()
    before = snapshot(name)
    try:
        db.run_migrations()
        raise AssertionError("trigger schema accepted")
    except RuntimeError:
        pass
    assert ledger(name) == [] and before == snapshot(name)
    RESULTS.append({"case": "unexpected_trigger", "blocked": True, "unchanged": True})
    variants = {
        "extra_check": "ALTER TABLE enology_mlf_plans ADD CONSTRAINT unexpected_check CHECK (volume_min_l > 1000)",
        "extra_column": "ALTER TABLE enology_mlf_plans ADD unexpected INT NULL",
        "wrong_collation": "ALTER TABLE enology_mlf_plans DEFAULT COLLATE utf8mb4_general_ci",
        "wrong_unique": "ALTER TABLE enology_mlf_plans DROP INDEX uq_enology_mlf_plan_lot, ADD INDEX uq_enology_mlf_plan_lot(wine_lot_id)",
        "wrong_fk": "ALTER TABLE enology_mlf_plans DROP FOREIGN KEY fk_enology_mlf_plan_lot, ADD CONSTRAINT wrong_lot_fk FOREIGN KEY(wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT",
    }
    for case, sql in variants.items():
        name = setup(case)
        c = connection(name)
        with c.cursor() as q:
            if case == "extra_check":
                q.execute("SET check_constraint_checks=OFF")
            q.execute(sql)
        c.commit()
        c.close()
        before = snapshot(name)
        try:
            db.run_migrations()
            raise AssertionError("invalid schema variant accepted: " + case)
        except RuntimeError:
            pass
        assert ledger(name) == [] and before == snapshot(name)
        RESULTS.append({"case": case, "blocked": True, "unchanged": True})
    name = setup("partial_table", table=False)
    c = connection(name)
    with c.cursor() as q:
        q.execute("CREATE TABLE enology_mlf_plans (id CHAR(36) PRIMARY KEY) ENGINE=InnoDB")
    c.commit()
    c.close()
    try:
        db.run_migrations()
        raise AssertionError("partial schema accepted")
    except RuntimeError:
        pass
    assert ledger(name) == []
    RESULTS.append({"case": "partial_table", "blocked": True, "no_false_ledger": True})
    print(json.dumps({"synthetic_only": True, "server": server, "cases": RESULTS}, indent=2))


if __name__ == "__main__":
    run()
