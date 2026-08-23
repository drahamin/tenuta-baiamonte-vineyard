from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MessagingIngestionIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        cls.intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        cls.bridge = (ROOT / "system_whatsapp" / "server.mjs").read_text(encoding="utf-8")
        cls.javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.intake_review = (ROOT / "app" / "static" / "assets" / "intake-review.js").read_text(encoding="utf-8")
        cls.lab_routes = (ROOT / "app" / "domains" / "laboratory_routes.py").read_text(encoding="utf-8")

    def test_analysis_claims_work_and_preserves_terminal_review_states(self) -> None:
        self.assertIn("def analyze_intake(record_id: str, *, allow_reanalysis: bool = False)", self.intelligence)
        self.assertIn("SET review_status='processing',processing_error=NULL", self.intelligence)
        self.assertIn("processing_error=NULL,updated_at=NOW(6)", self.intelligence)
        self.assertIn("review_status='processing' AND updated_at<DATE_SUB(NOW(),INTERVAL 10 MINUTE)", self.intelligence)
        self.assertGreaterEqual(self.intelligence.count("AND review_status='processing'"), 3)
        self.assertIn("\"superseded\": True", self.intelligence)
        self.assertIn("allow_reanalysis=True", self.main)

    def test_only_managers_can_decide_whatsapp_intake(self) -> None:
        self.assertIn('if profile == "manager" and (approval or rejection):', self.main)
        self.assertNotIn('if profile in {"manager", "reporter"} and (approval or rejection):', self.main)
        self.assertIn('if profile == "reporter":', self.main)
        self.assertIn("Submitted for manager review.", self.main)

    def test_unlisted_senders_are_quarantined_without_automation(self) -> None:
        self.assertIn("def quarantine_intake", self.intelligence)
        self.assertIn("classification='untrusted_sender'", self.intelligence)
        self.assertIn("Sender is not on the configured Gmail allowlist", self.intelligence)
        self.assertIn("Sender is not on the configured WhatsApp allowlist", self.main)
        self.assertIn("def _whatsapp_sender_is_allowed", self.main)
        self.assertIn('in {"reception", "reporter", "manager"}', self.main)
        self.assertIn("sender_allowed = _whatsapp_sender_is_allowed(sender, allowed, sender_assignment)", self.main)
        self.assertIn('route = "quarantine" if not sender_allowed', self.main)
        self.assertIn("if sender_allowed and not group_id:", self.main)

    def test_invitation_start_commands_open_the_local_menu(self) -> None:
        self.assertIn('"start", "inizia"', self.main)
        self.assertIn("Send keep-alive request", (ROOT / "app" / "static" / "assets" / "messaging.js").read_text(encoding="utf-8"))
        self.assertIn("they must reply START", (ROOT / "app" / "static" / "assets" / "messaging.js").read_text(encoding="utf-8"))

    def test_prepared_gmail_reply_reveals_collapsed_communications(self) -> None:
        self.assertIn("channelButton?.closest('details')?.setAttribute('open','')", self.javascript)
        self.assertIn("form.closest('details')?.setAttribute('open','')", self.javascript)

    def test_contact_search_can_hide_compact_cards(self) -> None:
        css = (ROOT / "app" / "static" / "control-center.css").read_text(encoding="utf-8")
        self.assertIn(".compact-contact[hidden]{display:none!important}", css)

    def test_meta_receiver_and_media_are_scoped(self) -> None:
        self.assertIn("expected_receiver_phone_number_id", self.main)
        self.assertIn("receiver_phone_number_id_mismatch", self.main)
        self.assertIn("_analyze_intake_background(record_id)", self.main)
        self.assertIn("elif settings.openai_api_key:", self.main)

    def test_failed_database_insert_removes_written_file(self) -> None:
        self.assertIn("path.unlink(missing_ok=True)", self.intelligence)

    def test_lab_intake_keeps_original_and_separates_every_wine(self) -> None:
        self.assertIn("identify every distinct physical sample or wine", self.intelligence)
        self.assertIn("never merge values from different columns", self.intelligence)
        self.assertIn("source_sample_label", self.intelligence)
        self.assertIn("function intakeSourcePreview", self.intake_review)
        self.assertIn("Reanalyze and separate samples", self.intake_review)
        self.assertIn("linked_records", self.main)
        self.assertIn("remaining_records", self.main)

    def test_lab_reports_and_measurements_are_deduplicated(self) -> None:
        self.assertIn("SELECT id FROM intake_items WHERE estate_id=%s AND file_sha256=%s", self.intelligence)
        self.assertIn("def _result_signature", self.lab_routes)
        self.assertIn('"duplicate": True', self.lab_routes)
        self.assertIn("existing_attachment", self.main)

    def test_intake_source_is_inline_with_explicit_download(self) -> None:
        self.assertIn("download: bool = Query(False)", self.main)
        self.assertIn('disposition = "attachment" if download else "inline"', self.main)
        self.assertIn("#intakeDialog .dialog-head .close", (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8"))

    def test_bridge_counts_only_accepted_intake(self) -> None:
        self.assertIn("return response.json().catch", self.bridge)
        self.assertIn("if (result?.accepted !== true) return;", self.bridge)
        self.assertLess(self.bridge.index("if (result?.accepted !== true) return;"), self.bridge.index("state.receivedCount += 1;"))

    def test_home_cards_are_bounded_and_future_work_is_not_recent(self) -> None:
        self.assertIn("LIMIT 6", self.main)
        self.assertIn("<= today_rome", self.main)
        self.assertIn("open.slice(0,6)", self.javascript)
        self.assertIn("activities||[]).slice(0,6)", self.javascript)


if __name__ == "__main__":
    unittest.main()
