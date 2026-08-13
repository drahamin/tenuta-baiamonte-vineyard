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


if __name__ == "__main__":
    unittest.main()
