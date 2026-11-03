import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


PATH = Path(__file__).parents[1] / "scripts/bootstrap_mobile_read_qualification.py"
SPEC = importlib.util.spec_from_file_location("mobile_qualification_bootstrap", PATH)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def stage(tmp_path, monkeypatch):
    # Bind the actual reviewed runner/module bytes; never synthesize credentials.
    root = Path(__file__).parents[1]
    sources = {"qualify_mobile_reporting_reads.py": root / "scripts/qualify_mobile_reporting_reads.py",
               "mobile_reporting_reads.py": root / "app/domains/mobile_reporting_reads.py"}
    for name, source in sources.items():
        (tmp_path / name).write_bytes(source.read_bytes())
    settings = SimpleNamespace(**{field: "synthetic" for field in bootstrap.FIELDS})
    settings.db_port = 3306
    settings.db_host, settings.db_name = "core-mariadb", "baiamonte_vineyard"
    calls = []
    module = SimpleNamespace(addon_version=lambda: "1.11.88", get_settings=lambda: settings,
                             runtime_option=lambda name, fallback: calls.append(name) or fallback)
    monkeypatch.setitem(sys.modules, "app.config", module)
    monkeypatch.setattr(bootstrap.sys, "argv", [])
    monkeypatch.setattr(bootstrap.sys, "path", list(sys.path))
    return module, settings, calls


def test_bootstrap_reads_only_bounded_existing_settings_and_executes_fixed_runner(tmp_path, monkeypatch):
    _, settings, calls = stage(tmp_path, monkeypatch)
    executed = []
    monkeypatch.setattr(bootstrap.runpy, "run_path", lambda path, **kw: executed.append((path, kw)))
    bootstrap.bootstrap(tmp_path)
    assert calls == list(bootstrap.FIELDS)
    assert executed == [(str(tmp_path / "qualify_mobile_reporting_reads.py"), {"run_name": "__main__"})]
    assert bootstrap.sys.argv[-1] == str(tmp_path / "mobile_reporting_reads.py")
    assert settings.db_port == 3306


def test_changed_runtime_fails_before_settings_access(tmp_path, monkeypatch):
    module, _, calls = stage(tmp_path, monkeypatch)
    module.addon_version = lambda: "1.11.89"
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap(tmp_path)
    assert calls == []


def test_changed_source_fails_before_import_or_execution(tmp_path, monkeypatch):
    _, _, calls = stage(tmp_path, monkeypatch)
    (tmp_path / "mobile_reporting_reads.py").write_text("raise RuntimeError('not approved')")
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap(tmp_path)
    assert calls == []


def test_other_database_destination_never_executes_runner(tmp_path, monkeypatch):
    module, _, _ = stage(tmp_path, monkeypatch)
    module.runtime_option = lambda name, fallback: "other.invalid" if name == "db_host" else fallback
    monkeypatch.setattr(bootstrap.runpy, "run_path", lambda *args, **kwargs: pytest.fail("off-scope execution"))
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap(tmp_path)
