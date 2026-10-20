#!/usr/bin/env python3
"""Build the paired ERP release twice and verify deterministic, private-safe output."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    run(sys.executable, str(root / "scripts/validate_release_pair.py"), str(root))
    run(sys.executable, str(root / "scripts/audit_erp_publication.py"), str(root / "baiamonte-secondary"))
    pair = json.loads((root / "release-pair.json").read_text(encoding="utf-8"))
    source_commit = os.environ.get("BAIAMONTE_SOURCE_COMMIT", "").strip()
    if not source_commit:
        source_commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    builder = root / "baiamonte-secondary/ops/build_release_artifact.py"
    with tempfile.TemporaryDirectory(prefix="baiamonte-release-test-") as temporary:
        temporary_path = Path(temporary)
        outputs = []
        for name in ("first", "second"):
            destination = temporary_path / name
            run(
                sys.executable, str(builder), "--source", str(root / pair["erp_source"]),
                "--output-dir", str(destination), "--version", pair["erp_version"],
                "--contract", str(pair["remote_contract"]),
                "--source-app-version", pair["vineyard_version"],
                "--source-commit", source_commit,
            )
            outputs.append(destination / f"baiamonte-secondary-{pair['erp_version']}.tar.gz")
        if outputs[0].read_bytes() != outputs[1].read_bytes():
            raise SystemExit("erp_release_test_failed: deterministic archives differ")
        with tarfile.open(outputs[0], "r:gz") as archive:
            names = set(archive.getnames())
        forbidden = {
            "config/config.php", ".release-public-key.b64",
            "ops/build_release_artifact.py", "ops/sign_release_manifest.sh",
        }
        if names & forbidden or any(name.startswith(("docs/", "ha_adapter/")) for name in names):
            raise SystemExit("erp_release_test_failed: private-only content entered archive")
        print(f"erp_release_test_ok sha256={sha256(outputs[0])} files={len(names)}")


if __name__ == "__main__":
    main()
