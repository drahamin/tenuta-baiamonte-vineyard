#!/usr/bin/env python3
"""One-shot OWNER host-console bootstrap, inside the existing Vineyard only.

No listener, environment/file writes, new credentials, startup or service action.
Existing DB settings stay in this on-host process and are never printed.
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys


EXPECTED = {
    "qualify_mobile_reporting_reads.py": "34e8a273b6ad9f6e4aac75bfbcda3f27698c86dbc84987f6e1a6b5657c40f23c",
    "mobile_reporting_reads.py": "406d3f77996891bc0523955eb8cdd6923a915e542a4a8c615f83691d633d8d48",
}
FIELDS = ("db_host", "db_port", "db_name", "db_user", "db_password", "estate_id", "tv_time_zone")


def bootstrap(directory: Path) -> None:
    for filename, expected in EXPECTED.items():
        path = directory / filename
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("staged file verification failed")
    sys.path.insert(0, "/opt/baiamonte")
    from app.config import addon_version, get_settings, runtime_option
    if addon_version() != "1.11.88":
        raise RuntimeError("runtime version changed; requalification required")
    settings = get_settings()
    # Same existing config loader as the app. Change this one-shot process's
    # settings object only; do not export secrets or modify production files.
    for field in FIELDS:
        setattr(settings, field, runtime_option(field, getattr(settings, field)))
    settings.db_port = int(settings.db_port)
    if (settings.db_host, settings.db_port, settings.db_name) != ("core-mariadb", 3306, "baiamonte_vineyard"):
        raise RuntimeError("database destination is outside the approved scope")
    sys.argv = [str(directory / "qualify_mobile_reporting_reads.py"), "--module", str(directory / "mobile_reporting_reads.py")]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    try:
        bootstrap(Path(__file__).resolve().parent)
    except Exception as error:
        print(json.dumps({"ok": False, "bootstrap_error_type": type(error).__name__}))
        raise SystemExit(2) from None
