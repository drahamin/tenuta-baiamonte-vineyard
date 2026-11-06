"""Explicit disposition of an immutable, unsafe historical migration.

235 remains packaged for audit. Its business changes are neither executed nor
asserted to have happened. 236 supplies only its required, verified schema.
"""
from hashlib import sha256
from pathlib import Path

RETIRED_MLF_MIGRATION = "235_red_malolactic_vp41_plans.sql"
MLF_SCHEMA_MIGRATION = "236_enology_mlf_schema_only.sql"
MLF_MIGRATION_DISPOSITION = {
    "retired_migration": RETIRED_MLF_MIGRATION,
    "retired_sha256": "b2da88221b73c4e183f334a5babdd13f6af18b2daf3000dc0c220783fa2e4638",
    "disposition": "retired_without_replay_schema_only_successor",
    "successor_migration": MLF_SCHEMA_MIGRATION,
    "successor_sha256": "de8a399b995485b33987fb9d120e3ccd794cf53ea077fc6dbeb0859b3a9d49ce",
    "business_reconciliation": "not_performed_requires_separate_source_evidence",
}


def validate_mlf_disposition(root: Path) -> None:
    """Verify both fixed files, independently of the mutable ledger."""
    for name, expected in (
        (RETIRED_MLF_MIGRATION, MLF_MIGRATION_DISPOSITION["retired_sha256"]),
        (MLF_SCHEMA_MIGRATION, MLF_MIGRATION_DISPOSITION["successor_sha256"]),
    ):
        path = root / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("MLF migration disposition artifact mismatch")
