from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SystemWhatsappTests(unittest.TestCase):
    def test_two_linked_accounts_remain_separate_from_meta(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        self.assertIn("for slot in (1, 2)", source)
        self.assertIn("separate_from_meta", source)
        self.assertIn("Separate from Meta Business", html)
        self.assertIn("[1, 2].map", bridge)

    def test_linked_account_sending_is_explicit_and_bounded(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if not account["send_enabled"]', source)
        self.assertIn("if (!state.chats.has(chatId))", bridge)
        self.assertIn("Allow sending from this account", javascript)
        self.assertIn("system-whatsapp-channel", source)

    def test_contacts_chat_and_membership_require_explicit_admin_action(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('/contacts", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/membership/refresh", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/membership/{request_id:path}", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn("groupRequestParticipantsUpdate", bridge)
        self.assertIn("groupAcceptInvite", bridge)
        self.assertIn("Membership review", javascript)
        self.assertIn("this WhatsApp membership request?", javascript)

    def test_messaging_and_social_administration_are_not_standard_navigation(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        for route in (
            '@app.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_admin)])',
            '@app.get("/api/v1/social", dependencies=[Depends(authorize_admin)])',
            '@app.post("/api/v1/social/facebook", dependencies=[Depends(authorize_admin)])',
            '@app.post("/api/v1/social/instagram", dependencies=[Depends(authorize_admin)])',
        ):
            self.assertIn(route, source)
        self.assertIn('data-view="whatsapp" data-admin data-nav-scope="admin" hidden', html)
        self.assertIn('data-view="social" data-admin data-nav-scope="admin" hidden', html)
        self.assertIn('id="view-whatsapp" data-admin hidden', html)
        self.assertIn('id="view-social" data-admin hidden', html)

    def test_selected_chat_ingestion_is_reviewed_and_deduplicated(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        self.assertIn("selected_chat_ids", source)
        self.assertIn("TIMESTAMPDIFF(SECOND,received_at,%s)", source)
        self.assertIn("file_sha256=%s", source)
        self.assertIn("ordinary greetings, acknowledgements, social conversation", intelligence)
        self.assertIn("quietly archived", intelligence)

    def test_each_account_has_an_enforced_contact_scope(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"contact_scope": "selected"', source)
        self.assertIn('"selected_contact_ids"', source)
        self.assertIn("_system_whatsapp_chat_allowed(account, chat_id", source)
        self.assertIn("All contacts", javascript)
        self.assertIn("Selected contacts only", javascript)
        self.assertIn("selected_contact_ids", javascript)

    def test_legacy_imessage_routes_and_workspace_are_removed(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('/api/v1/communications/imessage', source)
        self.assertNotIn('/webhooks/imessage', source)
        self.assertNotIn('data-communication="imessage"', html)


if __name__ == "__main__":
    unittest.main()
