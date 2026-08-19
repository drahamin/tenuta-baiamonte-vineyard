import unittest
import io
import json
import urllib.error
from pathlib import Path

from app.meta_errors import meta_error
from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class WhatsappSenderStateTests(unittest.TestCase):
    def test_runtime_settings_are_merged_instead_of_replaced(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("current.update(loaded)", source)
        self.assertIn("current.update(values)", source)
        self.assertIn("json.dumps(current", source)

    def test_inbound_and_outbound_health_are_sender_scoped(self) -> None:
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        frontend = frontend_source(ROOT)
        self.assertIn('details.get("phone_number_id")', main)
        self.assertIn('"phone_number_id": receiver_phone_number_id or None', main)
        self.assertGreaterEqual(intelligence.count('"phone_number_id": phone_number_id'), 2)
        self.assertIn('class="channel-status-lights"', frontend)
        self.assertNotIn("outbound sent", frontend)

    def test_verified_production_sender_has_non_persisting_registration_flow(self) -> None:
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        registration = (ROOT / "app" / "whatsapp_registration.py").read_text(encoding="utf-8")
        frontend = frontend_source(ROOT)
        self.assertIn('whatsapp_router', main)
        self.assertIn('/api/v1/communications/whatsapp/register', registration)
        self.assertIn('"messaging_product": "whatsapp", "pin": clean_pin', intelligence)
        self.assertIn('"pin_persisted": False', registration)
        self.assertIn("code_verification_status,platform_type,name_status", intelligence)
        self.assertIn("account_review_status,business_verification_status,ownership_type,country", intelligence)
        self.assertIn('business_verification_status and business_verification_status != "VERIFIED"', intelligence)
        self.assertIn('account_review_status and account_review_status != "APPROVED"', intelligence)
        self.assertIn('id="whatsappRegistrationForm"', frontend)
        self.assertIn('autocomplete="new-password"', frontend)
        self.assertIn("registrationForm.reset()", frontend)
        self.assertIn("Open WABA review", frontend)

    def test_meta_error_preserves_safe_registration_detail(self) -> None:
        payload = {
            "error": {
                "message": "(#100) Invalid parameter",
                "code": 100,
                "error_subcode": 2494010,
                "error_user_title": "Registration failed",
                "error_data": {"details": "The display name must be approved before registration."},
            }
        }
        error = urllib.error.HTTPError(
            "https://graph.facebook.com/v23.0/123/register",
            400,
            "Bad Request",
            {},
            io.BytesIO(json.dumps(payload).encode()),
        )
        message = meta_error(error)
        self.assertIn("Registration failed", message)
        self.assertIn("display name must be approved", message)
        self.assertIn("(#100) Invalid parameter", message)
        self.assertIn("Meta code 100/2494010", message)


if __name__ == "__main__":
    unittest.main()
