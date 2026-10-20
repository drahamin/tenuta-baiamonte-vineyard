#!/usr/bin/env python3
"""Fail closed if the proposed public ERP subtree contains private material."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ALLOWED_TOP_LEVEL = {"README.md", "composer.json", "config", "db", "ops", "public", "src", "tests", "vendor"}
FORBIDDEN_NAMES = {
    ".env", ".release-public-key.b64", "config.php", "id_rsa", "id_ed25519",
    "authorized_keys", "known_hosts", "deployment-status-2026-10-20.md",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".dump", ".bak", ".sqlite", ".sqlite3"}
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".php", ".py", ".sh", ".sql", ".txt", ".xml", ".yaml", ".yml"}
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "GitHub token": re.compile(r"\bgh[oprsu]_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "private IPv4 address": re.compile(r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b"),
    "Studio user path": re.compile(r"/Users/[^/\s]+/"),
    "cPanel account path": re.compile(r"/home/tenuoboe(?:/|\b)"),
    "private database principal": re.compile(r"\btenuoboe_[A-Za-z0-9_]+\b"),
    "production user identity": re.compile(r"\b(?:david|rahamin)\b", re.IGNORECASE),
    "production camera entity": re.compile(r"camera\.(?:vineyard_north|west_360|bbq_grill_2|kitchen|west_etna_view|east_360|gate_doorbell_2|rear_gate|top_vineyard_360|fox_ally|mid_vineyard_north|cisterna|192_168_0_54)\b"),
}


def fail(message: str) -> None:
    raise SystemExit(f"erp_publication_audit_failed: {message}")


def main() -> None:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "baiamonte-secondary"
    if not source.is_dir() or source.is_symlink():
        fail("source must be a real directory")
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if relative.parts[0] not in ALLOWED_TOP_LEVEL:
            fail(f"unexpected top-level path: {relative}")
        if path.is_symlink():
            fail(f"symlink is forbidden: {relative}")
        if path.is_dir():
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(f"private filename is forbidden: {relative}")
        if path.stat().st_size > 2 * 1024 * 1024:
            fail(f"unexpected large file: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"README.md", "composer.json"}:
            text = path.read_text(encoding="utf-8")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    fail(f"{label} in {relative}")

    example = (source / "config/config.example.php").read_text(encoding="utf-8")
    required_environment_keys = ["BAIAMONTE_DB_PASSWORD", "BAIAMONTE_SYNC_HMAC_KEY", "BAIAMONTE_CAMERA_HMAC_KEY", "BAIAMONTE_RELEASE_PUBLIC_KEY"]
    if any(f"getenv('{name}')" not in example for name in required_environment_keys):
        fail("example config must source every credential from the environment")
    if not re.search(r"'camera_allowlist'\s*=>\s*\[\s*\]", example):
        fail("public example camera allowlist must be empty")
    print(f"erp_publication_audit_ok files={sum(1 for path in source.rglob('*') if path.is_file())}")


if __name__ == "__main__":
    main()
