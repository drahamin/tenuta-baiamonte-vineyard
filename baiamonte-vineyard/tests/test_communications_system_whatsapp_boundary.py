from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.access import authorize_admin
from app.domains import communications_system_whatsapp_routes as routes
from app.domains.system_whatsapp_control import system_whatsapp_chat_allowed
from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_system_whatsapp_routes_are_unique_and_protected() -> None:
    expected = {
        ("/api/v1/communications/system-whatsapp", ("GET",)),
        ("/api/v1/communications/system-whatsapp/settings", ("PUT",)),
        ("/api/v1/communications/system-whatsapp/{slot}/connect", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/disconnect", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/relink", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/backup", ("GET",)),
        ("/api/v1/communications/system-whatsapp/{slot}/contacts", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/contacts/import", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/catalog/refresh", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/contacts/{contact_id:path}", ("PUT",)),
        ("/api/v1/communications/system-whatsapp/{slot}/history/sync", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/chats/{chat_id:path}", ("GET",)),
        ("/api/v1/communications/system-whatsapp/{slot}/membership/refresh", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/membership/{request_id:path}", ("POST",)),
        ("/api/v1/communications/system-whatsapp/{slot}/send", ("POST",)),
    }
    found = {}
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/v1/communications/system-whatsapp"):
            key = (route.path, tuple(sorted(route.methods or ())))
            assert key not in found
            found[key] = route.dependencies[0].dependency
    assert set(found) == expected
    assert all(dependency is authorize_admin for dependency in found.values())

    inbound = [route for route in app.routes if getattr(route, "path", "") == "/internal/system-whatsapp/inbound"]
    assert len(inbound) == 1
    assert tuple(sorted(inbound[0].methods or ())) == ("POST",)


def test_main_delegates_system_whatsapp_and_keeps_cached_aggregate() -> None:
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    aggregate = (ROOT / "app" / "domains" / "communications_meta_routes.py").read_text(encoding="utf-8")
    assert "app.include_router(communications_system_whatsapp_router)" in source
    assert '@app.get("/api/v1/communications/system-whatsapp"' not in source
    assert "system_whatsapp_center(settings)" in aggregate
    assert '@router.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_admin)])' in aggregate


def test_account_and_chat_scope_guards_remain_enforced() -> None:
    with pytest.raises(HTTPException) as unknown:
        routes._slot(3)
    assert unknown.value.status_code == 404

    account = {
        "monitor_all": False,
        "selected_chat_ids": ["estate@g.us"],
        "contact_scope": "selected",
        "selected_contact_ids": ["worker@s.whatsapp.net"],
    }
    assert system_whatsapp_chat_allowed(account, "estate@g.us")
    assert not system_whatsapp_chat_allowed(account, "other@g.us")
    assert system_whatsapp_chat_allowed(account, "worker@s.whatsapp.net")
    assert not system_whatsapp_chat_allowed(account, "unknown@s.whatsapp.net")


def test_sending_stays_disabled_until_explicitly_enabled() -> None:
    settings = {"accounts": [{"slot": 1, "send_enabled": False}]}
    with patch.object(routes, "system_whatsapp_settings", return_value=settings):
        with pytest.raises(HTTPException) as blocked:
            routes.communication_send_system_whatsapp(1, {"chat_id": "worker@s.whatsapp.net", "body": "Hello"}, None)
    assert blocked.value.status_code == 403


def test_inbound_bridge_requires_the_private_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_WHATSAPP_BRIDGE_TOKEN", "correct-token")
    with pytest.raises(HTTPException) as forbidden:
        routes.system_whatsapp_inbound(
            {"account_slot": 1},
            BackgroundTasks(),
            x_system_whatsapp_token="wrong-token",
            settings=object(),
        )
    assert forbidden.value.status_code == 403
