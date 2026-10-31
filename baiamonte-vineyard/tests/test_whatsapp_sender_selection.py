import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import intelligence


def _settings(**overrides):
    values = {
        "whatsapp_access_token": "production-token",
        "whatsapp_phone_number_id": "111",
        "whatsapp_business_account_id": "222",
        "whatsapp_test_access_token": "",
        "whatsapp_test_phone_number_id": "333",
        "whatsapp_test_business_account_id": "444",
        "whatsapp_test_display_phone_number": "+1 555 000 0000",
        "whatsapp_graph_api_version": "v23.0",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class WhatsappSenderSelectionTests(unittest.TestCase):
    def tearDown(self):
        intelligence.clear_whatsapp_cache()

    def test_stale_test_selection_falls_back_when_test_token_is_missing(self):
        runtime = {
            "whatsapp_active_phone_number_id": "333",
            "whatsapp_active_business_account_id": "444",
        }
        with (
            patch.object(intelligence, "get_settings", return_value=_settings()),
            patch.object(intelligence, "runtime_option", side_effect=lambda key, default=None: runtime.get(key, default)),
        ):
            self.assertEqual(intelligence.whatsapp_phone_number_id(), "111")
            self.assertEqual(intelligence.whatsapp_business_account_id(), "222")
            self.assertEqual(intelligence.whatsapp_access_token(), "production-token")

    def test_test_selection_is_preserved_with_its_own_token(self):
        runtime = {
            "whatsapp_active_phone_number_id": "333",
            "whatsapp_active_business_account_id": "444",
        }
        with (
            patch.object(intelligence, "get_settings", return_value=_settings(whatsapp_test_access_token="test-token")),
            patch.object(intelligence, "runtime_option", side_effect=lambda key, default=None: runtime.get(key, default)),
        ):
            self.assertEqual(intelligence.whatsapp_phone_number_id(), "333")
            self.assertEqual(intelligence.whatsapp_business_account_id(), "444")
            self.assertEqual(intelligence.whatsapp_access_token(), "test-token")

    def test_sender_catalog_does_not_probe_test_waba_with_production_token(self):
        requested_urls = []

        def urlopen(request, timeout=0):
            requested_urls.append(request.full_url)
            if request.full_url.endswith("/phone_numbers?fields=id,display_phone_number,verified_name,quality_rating,code_verification_status,platform_type,name_status&limit=100"):
                return _Response({"data": [{"id": "111", "display_phone_number": "+39 111"}]})
            return _Response({"id": "222", "name": "Production"})

        with (
            patch.object(intelligence, "get_settings", return_value=_settings()),
            patch.object(intelligence, "runtime_option", side_effect=lambda key, default=None: default),
            patch.object(intelligence.urllib.request, "urlopen", side_effect=urlopen),
        ):
            result = intelligence.whatsapp_phone_numbers(force=True)

        self.assertTrue(result["configured"])
        self.assertEqual([sender["id"] for sender in result["senders"]], ["111"])
        self.assertTrue(all("/444" not in url for url in requested_urls))
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
