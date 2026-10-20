#!/usr/bin/env python3
"""Validate the reviewed Vineyard/ERP release tuple."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys


VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ERP_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+\.[1-9][0-9]*$")


def fail(message: str) -> None:
    raise SystemExit(f"release_pair_invalid: {message}")


def assigned_integer(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                return node.value.value
    fail(f"{name} must be a literal integer in {path.relative_to(path.parents[2])}")


def main() -> None:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    descriptor = json.loads((root / "release-pair.json").read_text(encoding="utf-8"))
    expected_keys = {"schema", "vineyard_version", "erp_version", "remote_contract", "erp_source"}
    if set(descriptor) != expected_keys or descriptor["schema"] != 1:
        fail("descriptor schema or fields are not exact")
    vineyard_version = descriptor["vineyard_version"]
    erp_version = descriptor["erp_version"]
    contract = descriptor["remote_contract"]
    if not isinstance(vineyard_version, str) or not VERSION.fullmatch(vineyard_version):
        fail("vineyard_version is invalid")
    if not isinstance(erp_version, str) or not ERP_VERSION.fullmatch(erp_version):
        fail("erp_version is invalid")
    if not erp_version.startswith(vineyard_version + "."):
        fail("ERP version must be paired to the Vineyard version")
    if not isinstance(contract, int) or contract < 1:
        fail("remote_contract is invalid")
    if descriptor["erp_source"] != "baiamonte-secondary":
        fail("ERP source path is not approved")

    config = (root / "baiamonte-vineyard/config.yaml").read_text(encoding="utf-8")
    changelog = (root / "baiamonte-vineyard/CHANGELOG.md").read_text(encoding="utf-8")
    config_match = re.search(r'^version:\s*"([^"]+)"', config, re.MULTILINE)
    changelog_match = re.search(r"^##\s+(\S+)", changelog, re.MULTILINE)
    if not config_match or not changelog_match:
        fail("Vineyard manifest or changelog version is missing")
    if {config_match.group(1), changelog_match.group(1), vineyard_version} != {vineyard_version}:
        fail("Vineyard manifest, changelog and release pair do not match")

    ha_contract = assigned_integer(root / "baiamonte-vineyard/app/remote_erp.py", "REMOTE_ERP_CONTRACT_VERSION")
    php = (root / "baiamonte-secondary/src/ReplicaService.php").read_text(encoding="utf-8")
    website_match = re.search(r"public const SUPPORTED_CONTRACT_VERSION\s*=\s*([0-9]+)\s*;", php)
    if not website_match:
        fail("website contract constant is missing")
    if ha_contract != contract or int(website_match.group(1)) != contract:
        fail("HA, website and release-pair contracts do not match")
    print(f"release_pair_ok vineyard={vineyard_version} erp={erp_version} contract={contract}")


if __name__ == "__main__":
    main()
