from pathlib import Path

from app.access import authorize, authorize_admin
from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_meta_communications_routes_are_unique_and_protected() -> None:
    expected = {
        ("/api/v1/communications", ("GET",)): authorize,
        ("/api/v1/communications/whatsapp/send", ("POST",)): authorize_admin,
        ("/api/v1/communications/whatsapp/sender", ("PUT",)): authorize_admin,
        ("/api/v1/communications/whatsapp/send-file", ("POST",)): authorize_admin,
        ("/api/v1/communications/whatsapp/broadcast", ("POST",)): authorize_admin,
        ("/api/v1/communications/whatsapp/groups", ("GET",)): authorize_admin,
        ("/api/v1/communications/whatsapp/groups", ("POST",)): authorize_admin,
        ("/api/v1/communications/whatsapp/groups/{group_id}/invite-link", ("GET",)): authorize_admin,
        ("/api/v1/communications/whatsapp/contacts", ("PUT",)): authorize_admin,
        ("/api/v1/communications/whatsapp/assistants", ("GET",)): authorize_admin,
        ("/api/v1/communications/whatsapp/assistants", ("PUT",)): authorize_admin,
        ("/api/v1/communications/whatsapp/assistants/invite", ("POST",)): authorize_admin,
        ("/api/v1/communications/whatsapp/register", ("POST",)): authorize_admin,
    }
    actual = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if path == "/api/v1/communications" or path.startswith("/api/v1/communications/whatsapp"):
            key = (path, tuple(sorted(route.methods or ())))
            assert key not in actual
            actual[key] = route.dependencies[0].dependency
    assert actual == expected


def test_signed_webhook_is_owned_outside_main() -> None:
    routes = [route for route in app.routes if getattr(route, "path", "") == "/webhooks/whatsapp"]
    assert {tuple(sorted(route.methods or ())) for route in routes} == {("GET",), ("POST",)}
    assert all(route.endpoint.__module__ == "app.domains.communications_meta_webhook_routes" for route in routes)
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assistant = (ROOT / "app" / "domains" / "communications_whatsapp_assistant.py").read_text(encoding="utf-8")
    assert "app.include_router(communications_meta_router)" in main
    assert "app.include_router(communications_meta_webhook_router)" in main
    assert '@app.get("/webhooks/whatsapp")' not in main
    assert "async def _handle_whatsapp_assistant" in assistant
    assert "from app.main" not in assistant
