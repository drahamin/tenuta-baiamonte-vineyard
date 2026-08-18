from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
PROXY = ROOT / "custom_components/baiamonte_branding/mcp_proxy.py"
INIT = ROOT / "custom_components/baiamonte_branding/__init__.py"


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

    def test_proxy_uses_supported_home_assistant_view_methods_only(self) -> None:
        source = PROXY.read_text(encoding="utf-8")
        self.assertIn("async def get(", source)
        self.assertIn("async def post(", source)
        self.assertIn("async def delete(", source)
        self.assertNotIn("async def options(", source)

    def test_branding_completes_before_proxy_registration(self) -> None:
        source = INIT.read_text(encoding="utf-8")
        restore_position = source.index('if options.get("restore", False):')
        apply_position = source.index("apply_branding", restore_position)
        register_position = source.index("hass.http.register_view")
        self.assertLess(apply_position, register_position)
        self.assertNotIn("return True", source[restore_position:register_position])


if __name__ == "__main__":
    unittest.main()
