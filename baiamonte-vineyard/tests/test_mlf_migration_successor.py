import ast
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from app import db
from app.domains import release_evidence
from app.migration_policy import MLF_MIGRATION_DISPOSITION, MLF_SCHEMA_MIGRATION, RETIRED_MLF_MIGRATION, validate_mlf_disposition
from app.sql_migrations import split_sql_statements
from test_release_evidence import _temporary_release, EXPECTED

ROOT = Path(__file__).resolve().parents[1]


def test_retirement_files_are_immutable_and_successor_is_schema_only(tmp_path):
    root = ROOT / "db/migrations"
    validate_mlf_disposition(root)
    for name in (RETIRED_MLF_MIGRATION, MLF_SCHEMA_MIGRATION):
        shutil.copyfile(root / name, tmp_path / name)
    statements = split_sql_statements((root / MLF_SCHEMA_MIGRATION).read_text())
    assert len(statements) == 1
    assert "CREATE TABLE IF NOT EXISTS enology_mlf_plans" in statements[0]
    for name in (RETIRED_MLF_MIGRATION, MLF_SCHEMA_MIGRATION):
        original = (tmp_path / name).read_bytes()
        (tmp_path / name).write_bytes(original + b"\n")
        with pytest.raises(ValueError, match="artifact mismatch"):
            validate_mlf_disposition(tmp_path)
        (tmp_path / name).write_bytes(original)


@pytest.mark.parametrize("allowlist", [None, "", RETIRED_MLF_MIGRATION, MLF_SCHEMA_MIGRATION + "," + RETIRED_MLF_MIGRATION])
def test_unsafe_or_unset_allowlist_refused_before_any_connection(monkeypatch, allowlist):
    if allowlist is None:
        monkeypatch.delenv("BAIAMONTE_MIGRATION_ALLOWLIST", raising=False)
    else:
        monkeypatch.setenv("BAIAMONTE_MIGRATION_ALLOWLIST", allowlist)
    def forbidden():
        raise AssertionError("must not connect")
    monkeypatch.setattr(db, "connect", forbidden)
    with pytest.raises(ValueError):
        db.run_migrations()


def test_hash_guard_precedes_database_connection(monkeypatch):
    monkeypatch.setenv("BAIAMONTE_MIGRATION_ALLOWLIST", MLF_SCHEMA_MIGRATION)
    def invalid(_root):
        raise ValueError("artifact mismatch")
    monkeypatch.setattr(db, "validate_mlf_disposition", invalid)
    monkeypatch.setattr(db, "connect", lambda: pytest.fail("must not connect"))
    with pytest.raises(ValueError, match="artifact mismatch"):
        db.run_migrations()


@pytest.mark.parametrize("session", [False, True, "true", None])
def test_startup_exact_allowlist_excludes_retired_migration(session):
    # Evaluate only the static allowlist AST, never startup or options access.
    tree = ast.parse((ROOT / "entrypoint.py").read_text())
    start = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "approved_migrations" for t in n.targets))
    nodes = tree.body[start:start + 3]
    env = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "allowlist", "exec"), {"options": {"mobile_site_session_schema_enabled": session}, "os": type("Env", (), {"environ": env})})
    actual = set(env["BAIAMONTE_MIGRATION_ALLOWLIST"].split(","))
    assert actual == EXPECTED | {MLF_SCHEMA_MIGRATION} | ({release_evidence.MOBILE_SESSION_MIGRATION} if session is True else set())
    assert RETIRED_MLF_MIGRATION not in actual


@pytest.mark.parametrize("failure", ["missing_mlf_shape", "bad_mlf_shape", "missing_successor_ledger", "missing_disposition", "altered_235", "altered_236", "missing_policy_hash"])
def test_release_gate_requires_successor_proof_and_real_schema(tmp_path, monkeypatch, failure):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    value = database()
    manifest = json.loads(manifest_path.read_text())
    if failure == "missing_mlf_shape":
        value.pop("mlf_schema")
    elif failure == "bad_mlf_shape":
        value["mlf_schema"] = {"ready": False}
    elif failure == "missing_successor_ledger":
        value["ledger"][MLF_SCHEMA_MIGRATION] = False
        value["legacy_235_ledger_applied"] = True
    elif failure == "missing_disposition":
        manifest.pop("migration_dispositions")
    elif failure == "missing_policy_hash":
        manifest["files"].pop("app/migration_policy.py")
    else:
        relative = "db/migrations/" + (RETIRED_MLF_MIGRATION if failure == "altered_235" else MLF_SCHEMA_MIGRATION)
        target = package / relative
        target.write_bytes(target.read_bytes() + b"\n")
        manifest["files"][relative] = sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setenv("BAIAMONTE_MIGRATION_ALLOWLIST", ",".join(EXPECTED | {MLF_SCHEMA_MIGRATION}))
    monkeypatch.setattr(release_evidence, "addon_version", lambda: "1.11.71")
    result = release_evidence.build_release_evidence(manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint, entrypoint_verified=True,
        expected_manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(), database_collector=lambda: value)
    assert result["ok"] is False


@pytest.mark.parametrize("legacy", [True, False, None])
def test_structural_readiness_does_not_claim_business_reconciliation(tmp_path, monkeypatch, legacy):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    value = database()
    value["legacy_235_ledger_applied"] = legacy
    monkeypatch.setenv("BAIAMONTE_MIGRATION_ALLOWLIST", ",".join(EXPECTED | {MLF_SCHEMA_MIGRATION}))
    monkeypatch.setattr(release_evidence, "addon_version", lambda: "1.11.71")
    result = release_evidence.build_release_evidence(manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint, entrypoint_verified=True,
        expected_manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(), database_collector=lambda: value)
    assert result["ok"] is True
    assert result["migration_gate"]["legacy_235_ledger_applied"] is legacy
    assert result["migration_gate"]["legacy_235_business_effects"] == "unknown_not_reconciled"
    assert result["migration_gate"]["mlf_disposition"] == MLF_MIGRATION_DISPOSITION
