import pathlib
import unittest

from app.whatsapp_policy import approved_whatsapp_template


class ApprovedWhatsappTemplateTests(unittest.TestCase):
    def setUp(self):
        self.templates = [
            {"name": "baiamonte_assistant_invitation", "language": "en", "status": "APPROVED", "category": "UTILITY"},
            {"name": "baiamonte_assistant_invitation", "language": "it", "status": "PENDING", "category": "UTILITY"},
            {"name": "other_template", "language": "it", "status": "APPROVED", "category": "UTILITY"},
            {"name": "parameterized_invitation", "language": "en", "status": "APPROVED", "category": "UTILITY", "components": [{"type": "BODY", "text": "Hello {{1}}"}]},
        ]

    def test_resolves_exact_approved_name_and_language(self):
        result = approved_whatsapp_template(self.templates, "baiamonte_assistant_invitation", "en")
        self.assertEqual(result["language"], "en")

    def test_rejects_pending_template(self):
        self.assertIsNone(approved_whatsapp_template(self.templates, "baiamonte_assistant_invitation", "it"))

    def test_rejects_unlisted_template(self):
        self.assertIsNone(approved_whatsapp_template(self.templates, "not_real", "en"))

    def test_rejects_parameterized_template(self):
        self.assertIsNone(approved_whatsapp_template(self.templates, "parameterized_invitation", "en"))

    def test_live_and_test_senders_remain_selectable(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        config = (root / "config.yaml").read_text()
        entrypoint = (root / "entrypoint.py").read_text()
        backend = (root / "app" / "intelligence.py").read_text()
        frontend = (root / "app" / "static" / "app.js").read_text()
        self.assertIn("whatsapp_test_phone_number_id", config)
        self.assertIn("whatsapp_test_business_account_id", config)
        self.assertIn('"whatsapp_test_access_token": "WHATSAPP_TEST_ACCESS_TOKEN"', entrypoint)
        self.assertIn('"whatsapp_test_phone_number_id": "WHATSAPP_TEST_PHONE_NUMBER_ID"', entrypoint)
        self.assertIn('"whatsapp_test_business_account_id": "WHATSAPP_TEST_BUSINESS_ACCOUNT_ID"', entrypoint)
        self.assertIn('(settings.whatsapp_business_account_id, False)', backend)
        self.assertIn('(settings.whatsapp_test_business_account_id, True)', backend)
        self.assertIn('"is_test": is_test', backend)
        self.assertIn('"business_account_id": account_id', backend)
        self.assertIn("whatsapp_business_account_id()", backend)
        self.assertIn("Choose the business or test number", frontend)
        self.assertIn("own approved template library", frontend)


if __name__ == "__main__":
    unittest.main()
