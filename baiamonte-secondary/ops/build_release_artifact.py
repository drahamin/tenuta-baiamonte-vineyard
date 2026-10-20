#!/usr/bin/env python3
"""Build a deterministic private-web release and its unsigned manifest."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile


RELEASE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {
    "config/config.php",
    ".release-public-key.b64",
    "ops/build_release_artifact.py",
    "ops/sign_release_manifest.sh",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def release_files(source: Path, output: Path) -> list[Path]:
    result: list[Path] = []
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        posix = relative.as_posix()
        if path == output or not path.is_file() or path.is_symlink():
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if posix in EXCLUDED_FILES or path.suffix == ".pyc":
            continue
        result.append(path)
    return sorted(result, key=lambda value: value.relative_to(source).as_posix())


def build_archive(source: Path, destination: Path) -> None:
    files = release_files(source, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in files:
                    relative = PurePosixPath(path.relative_to(source).as_posix())
                    info = archive.gettarinfo(str(path), arcname=str(relative))
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = 0
                    info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--contract", type=int, default=1)
    parser.add_argument("--source-app-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--schema-changes-required", action="store_true")
    arguments = parser.parse_args()
    if not RELEASE_RE.fullmatch(arguments.version) or arguments.contract < 1:
        raise SystemExit("invalid release version or contract")
    source = Path(arguments.source).resolve()
    output_dir = Path(arguments.output_dir).resolve()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}(?:[0-9A-Za-z._-]*)", arguments.source_app_version):
        raise SystemExit("invalid source application version")
    if not re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?", arguments.source_commit):
        raise SystemExit("invalid source commit")
    javascript = sorted((source / "public").glob("*.js"))
    for path in javascript:
        subprocess.run(["node", "--check", str(path)], check=True)
    artifact = output_dir / f"baiamonte-secondary-{arguments.version}.tar.gz"
    build_archive(source, artifact)

    migrations = []
    for migration in sorted((source / "db").glob("migration-*.sql")):
        migrations.append({
            "id": migration.stem,
            "path": migration.relative_to(source).as_posix(),
            "sha256": digest(migration),
            "automatic": False,
        })
    payload = {
        "schema": 1,
        "product": "baiamonte-secondary",
        "version": arguments.version,
        "remote_contract_min": arguments.contract,
        "remote_contract_max": arguments.contract,
        "source_app_version": arguments.source_app_version,
        "source_commit": arguments.source_commit,
        "schema_changes_required": arguments.schema_changes_required,
        "publisher_checks": {"javascript_syntax": "passed"},
        "artifact": {
            "filename": artifact.name,
            "sha256": digest(artifact),
            "size": artifact.stat().st_size,
        },
        "required_files": [
            "public/index.php", "public/harvest.js", "src/ReplicaService.php",
            "tests/run.php", "ops/website_preflight.php",
        ],
        "migrations": migrations,
    }
    manifest = output_dir / f"baiamonte-secondary-{arguments.version}.manifest.json"
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), "manifest": str(manifest), **payload["artifact"]}, sort_keys=True))


if __name__ == "__main__":
    main()
