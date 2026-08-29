from pathlib import Path
import unittest

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


def system_whatsapp_backend_source() -> str:
    return "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "app/main.py",
            "app/domains/communications_meta_routes.py",
            "app/domains/communications_meta_webhook_routes.py",
            "app/domains/communications_whatsapp_assistant.py",
            "app/domains/system_whatsapp_control.py",
            "app/domains/communications_system_whatsapp_routes.py",
            "app/domains/social_routes.py",
        )
    )


class SystemWhatsappTests(unittest.TestCase):
    def test_early_messaging_bundle_does_not_call_main_application_helpers(self) -> None:
        messaging = (ROOT / "app" / "static" / "assets" / "messaging.js").read_text(encoding="utf-8")
        app = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("$('grapeHistoryMeasure')", messaging)
        self.assertNotIn("$('cellarHistoryMeasure')", messaging)
        self.assertIn("$('grapeHistoryMeasure').onchange=()=>window.renderGrapeHistory?.()", app)
        self.assertIn("$('cellarHistoryMeasure').onchange=()=>window.renderCellarHistory?.()", app)

    def test_baileys_socket_factory_supports_alpine_export_shapes(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        package = (ROOT / "system_whatsapp" / "package.json").read_text(encoding="utf-8")
        self.assertIn("import * as BaileysModule", bridge)
        self.assertIn("BaileysModule.default?.default", bridge)
        self.assertIn("typeof value === 'function'", bridge)
        self.assertNotIn("import makeWASocket,", bridge)
        self.assertIn('\"@whiskeysockets/baileys\": \"6.7.24\"', package)

    def test_qr_pairing_uses_current_whatsapp_web_version_and_bounded_retries(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        self.assertIn("fetchLatestWaWebVersion", bridge)
        self.assertIn("version,", bridge)
        self.assertIn("timeout: 15000", bridge)
        self.assertIn("state.reconnectAttempts < 5", bridge)
        self.assertIn("HTTP ${code}", bridge)

    def test_linked_account_catalog_and_history_are_synchronized_and_retained(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        source = system_whatsapp_backend_source()
        javascript = frontend_source(ROOT)
        self.assertIn("groupFetchAllParticipating", bridge)
        self.assertIn("syncFullHistory: true", bridge)
        self.assertIn("shouldSyncHistoryMessage: () => true", bridge)
        self.assertIn("catalog.json", bridge)
        self.assertIn('system_whatsapp_refresh_catalog', source)
        self.assertIn('/catalog/refresh", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn("Sync names & groups", javascript)
        self.assertIn("Check the groups to ingest", javascript)

    def test_contact_names_and_prior_chat_sync_survive_lid_addressing(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        source = system_whatsapp_backend_source()
        javascript = frontend_source(ROOT)
        self.assertIn("rememberContact(state, senderJid, [item.pushName]", bridge)
        self.assertIn("getPNForLID", bridge)
        self.assertIn("getLIDForPN", bridge)
        self.assertIn("remoteJidAlt", bridge)
        self.assertIn("participantAlt", bridge)
        self.assertIn("lid-mapping.update", bridge)
        self.assertIn("event.type === 'notify'", bridge)
        self.assertIn("syncPriorChats", bridge)
        self.assertIn("history_message_count", bridge)
        self.assertIn("system_whatsapp_sync_history", source)
        self.assertIn("system_whatsapp_rename_contact", source)
        self.assertIn("Sync prior chats", javascript)
        self.assertIn("data-system-wa-rename", javascript)

    def test_phone_contact_import_backup_and_safe_relink_are_available(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        source = system_whatsapp_backend_source()
        javascript = frontend_source(ROOT)
        self.assertIn("importContactNames", bridge)
        self.assertIn("accountBackup", bridge)
        self.assertIn("relinkAccount", bridge)
        self.assertIn('/contacts/import", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/backup", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/relink", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn("parseVcardContacts", javascript)
        self.assertIn("Import phone contacts", javascript)
        self.assertIn("Back up chats", javascript)
        self.assertIn("Save account settings", javascript)

    def test_group_history_and_members_are_prioritized(self) -> None:
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn("left.endsWith('@g.us') ? 0 : 1", bridge)
        self.assertIn("groupRequested", bridge)
        self.assertIn("participant_count: participants.length", bridge)
        self.assertIn("participants: participants.length", bridge)
        self.assertIn("await state.socket.groupMetadata(groupId)", bridge)
        self.assertIn("group-participants.update", bridge)
        self.assertIn("system-group-members", javascript)
        self.assertIn("Member names unavailable", javascript)
        self.assertIn("Remove address-book rows from older imports", bridge)

    def test_two_linked_accounts_remain_separate_from_meta(self) -> None:
        source = system_whatsapp_backend_source()
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        self.assertIn("for slot in (1, 2)", source)
        self.assertIn("separate_from_meta", source)
        self.assertIn("Separate from Meta Business", html)
        self.assertIn("[1, 2].map", bridge)

    def test_linked_account_sending_is_explicit_and_bounded(self) -> None:
        source = system_whatsapp_backend_source()
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn('if not account["send_enabled"]', source)
        self.assertIn("if (!state.chats.has(chatId))", bridge)
        self.assertIn("Allow sending from this account", javascript)
        self.assertIn("system-whatsapp-channel", source)

    def test_contacts_chat_and_membership_require_explicit_admin_action(self) -> None:
        source = system_whatsapp_backend_source()
        bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn('/contacts", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/membership/refresh", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn('/membership/{request_id:path}", dependencies=[Depends(authorize_admin)]', source)
        self.assertIn("groupRequestParticipantsUpdate", bridge)
        self.assertIn("groupAcceptInvite", bridge)
        self.assertIn("Membership review", javascript)
        self.assertIn("this WhatsApp membership request?", javascript)

    def test_messaging_and_social_administration_are_not_standard_navigation(self) -> None:
        source = system_whatsapp_backend_source()
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        for route in (
            '@router.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_admin)])',
            '@router.get("", dependencies=[Depends(authorize_admin)])',
            '@router.post("/facebook", dependencies=[Depends(authorize_admin)])',
            '@router.post("/instagram", dependencies=[Depends(authorize_admin)])',
        ):
            self.assertIn(route, source)
        self.assertRegex(html, r'data-view="whatsapp" data-admin data-nav-scope="admin"[^>]* hidden')
        self.assertRegex(html, r'data-view="social" data-admin data-nav-scope="admin"[^>]* hidden')
        self.assertIn('id="view-whatsapp" data-admin hidden', html)
        self.assertIn('id="view-social" data-admin hidden', html)

    def test_selected_chat_ingestion_is_reviewed_and_deduplicated(self) -> None:
        source = system_whatsapp_backend_source()
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        self.assertIn("selected_chat_ids", source)
        self.assertIn("TIMESTAMPDIFF(SECOND,received_at,%s)", source)
        self.assertIn("file_sha256=%s", source)
        self.assertIn("ordinary greetings, acknowledgements, social conversation", intelligence)
        self.assertIn("quietly archived", intelligence)

    def test_each_account_has_an_enforced_contact_scope(self) -> None:
        source = system_whatsapp_backend_source()
        javascript = frontend_source(ROOT)
        self.assertIn('"contact_scope": "selected"', source)
        self.assertIn('"selected_contact_ids"', source)
        self.assertIn("system_whatsapp_chat_allowed(account, chat_id", source)
        self.assertIn("All contacts", javascript)
        self.assertIn("Selected contacts only", javascript)
        self.assertIn("selected_contact_ids", javascript)

    def test_legacy_imessage_routes_and_workspace_are_removed(self) -> None:
        source = system_whatsapp_backend_source()
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('/api/v1/communications/imessage', source)
        self.assertNotIn('/webhooks/imessage', source)
        self.assertNotIn('data-communication="imessage"', html)

    def test_system_account_sections_and_chat_dialog_fit_mobile_viewports(self) -> None:
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".system-account-workspace{display:grid;grid-template-columns:1fr", css)
        self.assertIn("#systemWhatsappChatDialog{box-sizing:border-box;width:min(680px,calc(100vw - 24px))", css)
        self.assertIn("#systemWhatsappChatDialog{width:calc(100vw - 12px)", css)
        self.assertIn(".system-chat-reply{grid-template-columns:1fr}", css)


if __name__ == "__main__":
    unittest.main()
