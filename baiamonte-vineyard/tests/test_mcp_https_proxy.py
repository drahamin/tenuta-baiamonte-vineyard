from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
PROXY = ROOT / "custom_components/baiamonte_branding/mcp_proxy.py"


class McpHttpsProxyPackagingTests(unittest.TestCase):
    def test_proxy_is_narrow_and_keeps_mcp_auth_and_session_headers(self) -> None:
        source = PROXY.read_text(encoding="utf-8")
        self.assertIn('url = "/api/baiamonte_mcp"', source)
        self.assertIn('"authorization"', source)
        self.assertIn('"mcp-session-id"', source)
        self.assertNotIn("3306", source)
        self.assertNotIn("/api/", source.replace('"/api/baiamonte_mcp"', ""))

    def test_proxy_does_not_disable_downstream_bearer_validation(self) -> None:
        source = PROXY.read_text(encoding="utf-8")
        self.assertNotIn("mcp_server_token", source)
        self.assertNotIn("Bearer ", source)


if __name__ == "__main__":
    unittest.main()
