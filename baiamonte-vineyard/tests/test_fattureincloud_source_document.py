import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_fattureincloud_module():
    replacements = {
        "app.config": {"get_settings": lambda: None},
        "app.db": {"fetch_one": lambda *_: None, "transaction": lambda: None},
        "app.inventory": {"convert_inventory_quantity": lambda *_: None},
        "app.service": {"estate_id": lambda: "estate", "new_id": lambda: "new-id"},
    }
    previous = {name: sys.modules.get(name) for name in replacements}
    try:
        for name, attributes in replacements.items():
            module = ModuleType(name)
            for key, value in attributes.items():
                setattr(module, key, value)
            sys.modules[name] = module
        name = "app._fattureincloud_source_document_test"
        path = Path(__file__).resolve().parents[1] / "app" / "fattureincloud.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


fattureincloud = _load_fattureincloud_module()


def test_fresh_received_document_url_uses_detail_endpoint(monkeypatch):
    monkeypatch.setattr(fattureincloud, "get_settings", lambda: SimpleNamespace(fattureincloud_token="token", fattureincloud_company_id="1189754"))
    calls = []
    monkeypatch.setattr(fattureincloud, "_get", lambda path, parameters: calls.append((path, parameters)) or {"data": {"url": "https://example.invalid/fresh.xml?signature=new"}})
    assert fattureincloud.fresh_source_document_url("444446634", "purchase_invoice").endswith("fresh.xml?signature=new")
    assert calls == [("/c/1189754/received_documents/444446634", {"fieldset": "detailed"})]


def test_fresh_issued_document_url_uses_issued_detail_endpoint(monkeypatch):
    monkeypatch.setattr(fattureincloud, "get_settings", lambda: SimpleNamespace(fattureincloud_token="token", fattureincloud_company_id="company"))
    calls = []
    monkeypatch.setattr(fattureincloud, "_get", lambda path, parameters: calls.append((path, parameters)) or {"data": {"attachment_url": {"download_url": "https://example.invalid/fresh"}}})
    assert fattureincloud.fresh_source_document_url("12", "credit_note").endswith("/fresh")
    assert calls == [("/c/company/issued_documents/12", {"fieldset": "detailed"})]


def test_stable_source_path_contains_no_expiring_credentials():
    path = fattureincloud.stable_source_document_path("doc id")
    assert path == "api/v1/finance/documents/doc%20id/original"
    assert "X-Amz" not in path and "token" not in path.casefold()


def test_document_upsert_persists_stable_route_not_temporary_url(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))

        def fetchone(self):
            return None

    cursor = Cursor()
    monkeypatch.setattr(fattureincloud, "_party", lambda *_: "party-id")
    monkeypatch.setattr(fattureincloud, "estate_id", lambda: "estate-id")
    monkeypatch.setattr(fattureincloud, "new_id", lambda: "local-document-id")
    item = {
        "id": 444446634,
        "invoice_number": "3133/00/2026",
        "date": "2026-10-31",
        "amount_net": 81.40,
        "amount_vat": 17.91,
        "amount_gross": 99.31,
        "currency": {"id": "EUR"},
        "url": "https://example.invalid/expired.xml?X-Amz-Security-Token=old",
    }
    assert fattureincloud._upsert_document(cursor, item, "purchase_invoice", "supplier") == "local-document-id"
    stored_source = cursor.calls[-1][1][-2]
    assert stored_source == "api/v1/finance/documents/local-document-id/original"
    assert "X-Amz" not in stored_source