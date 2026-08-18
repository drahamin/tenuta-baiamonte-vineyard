from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile


async def save_workbook_upload(upload: UploadFile, destination: Path) -> None:
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, "Only Excel .xlsx or .xlsm workbooks are accepted")
    size = 0
    with destination.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > 25 * 1024 * 1024:
                raise HTTPException(413, "Each workbook must be 25 MB or smaller")
            handle.write(chunk)
    await upload.close()


def supplied_workbook(upload: UploadFile | None) -> bool:
    return upload is not None and bool((upload.filename or "").strip())


def run_workbook_import(command: list[str], working_directory: Path) -> None:
    try:
        result = subprocess.run(command, cwd=working_directory, env=os.environ.copy(), capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "Workbook validation exceeded five minutes") from error
    if result.returncode:
        message = (result.stderr or result.stdout or "Workbook import failed").strip().splitlines()[-1]
        raise HTTPException(422, message[:500])


async def import_uploaded_workbooks(commit: bool, confirmation: str, uploads: dict[str, UploadFile | None]) -> dict[str, Any]:
    if not any(supplied_workbook(upload) for upload in uploads.values()):
        raise HTTPException(422, "Select at least one workbook")
    if commit and confirmation != "BACKUP VERIFIED":
        raise HTTPException(409, "Confirm that the Home Assistant backup completed before importing")
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    reports: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="baiamonte-import-") as temp_name:
        temp_dir = Path(temp_name)
        uploaded: dict[str, Path] = {}
        for label, upload in uploads.items():
            if supplied_workbook(upload):
                path = temp_dir / f"{label}.xlsx"
                await save_workbook_upload(upload, path)
                uploaded[label] = path
        if "vineyard" in uploaded:
            report_path = temp_dir / "vineyard-report.json"
            command = [sys.executable, str(scripts_dir / "import_workbook.py"), str(uploaded["vineyard"]), "--report", str(report_path)]
            if commit:
                command.append("--commit")
            await asyncio.to_thread(run_workbook_import, command, scripts_dir)
            reports["vineyard"] = json.loads(report_path.read_text(encoding="utf-8"))
        finance_paths = [uploaded[label] for label in ("finance", "funding") if label in uploaded]
        if finance_paths:
            report_path = temp_dir / "finance-report.json"
            command = [sys.executable, str(scripts_dir / "import_finance_workbooks.py"), *(str(path) for path in finance_paths), "--report", str(report_path)]
            if commit:
                command.append("--commit")
            await asyncio.to_thread(run_workbook_import, command, scripts_dir)
            reports["finance_funding"] = json.loads(report_path.read_text(encoding="utf-8"))
        if any(label in uploaded for label in ("legacy_work", "legacy_costs")):
            report_path = temp_dir / "legacy-costs-report.json"
            command = [sys.executable, str(scripts_dir / "import_legacy_costs.py")]
            for label, flag in (("legacy_work", "--work-history"), ("legacy_costs", "--costs-history")):
                if label in uploaded:
                    command.extend([flag, str(uploaded[label])])
            command.extend(["--report", str(report_path)])
            if commit:
                command.append("--commit")
            await asyncio.to_thread(run_workbook_import, command, scripts_dir)
            reports["legacy_baiamonte_costs"] = json.loads(report_path.read_text(encoding="utf-8"))
    return {"mode": "commit" if commit else "dry-run", "reports": reports}
