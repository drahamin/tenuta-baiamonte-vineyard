from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SystemDocumentationTests(unittest.TestCase):
    def test_admin_documentation_is_protected_and_does_not_return_secrets(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"/api/v1/admin/system-documentation"', source)
        self.assertIn("Depends(authorize_admin)", source)
        self.assertIn('"configured": _configured(settings.mcp_server_token)', source)
        endpoint = source.split("def system_documentation()", 1)[1].split('@app.get("/api/v1/admin/control"', 1)[0]
        self.assertNotIn('"value": settings.', endpoint)
        self.assertNotIn('"token": settings.', endpoint)
        self.assertNotIn('"password": settings.', endpoint)

    def test_admin_documentation_ui_contains_live_reference_sections(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn('data-view="admin-docs"', html)
        self.assertIn('id="view-admin-docs"', html)
        for element_id in ("systemDocsServices", "systemDocsCredentials", "systemDocsApis", "systemDocsAccess", "systemDocsLinks"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("loadSystemDocs", javascript)
        self.assertIn("renderSystemDocs", javascript)
        self.assertIn("system-doc-grid", css)
        hospitality_docs = (ROOT / "app" / "domains" / "system_docs.py").read_text(encoding="utf-8")
        self.assertIn('"Hospitality Managers"', hospitality_docs)
        self.assertIn('/api/v1/hospitality/dashboard', hospitality_docs)
        self.assertIn("RELEASE 1.6.42", html)
        self.assertIn("pageCount=37", (ROOT / "app/static/app.js").read_text())

    def test_system_manual_can_be_viewed_or_downloaded_from_docs(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        manual = ROOT / "docs" / "Tenuta_Baiamonte_System_Manual.pdf"

        self.assertTrue(manual.is_file())
        self.assertGreater(manual.stat().st_size, 100_000)
        self.assertIn('"/api/v1/admin/system-manual.pdf"', source)
        self.assertIn("Depends(authorize_admin)", source)
        self.assertIn('disposition = "attachment" if download else "inline"', source)
        self.assertIn('id="systemManualView"', html)
        self.assertIn('id="systemManualDialog"', html)
        self.assertIn('id="systemManualPages"', html)
        self.assertNotIn('id="systemManualFrame"', html)
        self.assertIn("openSystemManual", javascript)
        self.assertIn("assets/manual-pages/page-", javascript)
        self.assertIn("overflow-y:auto", (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8"))
        pages = sorted((ROOT / "app" / "static" / "manual-pages").glob("page-*.webp"))
        self.assertEqual(len(pages), 37)
        self.assertTrue(all(page.stat().st_size > 20_000 for page in pages))
        self.assertIn("COPY docs docs", dockerfile)

    def test_system_manual_build_includes_complete_1_6_release_history(self) -> None:
        manual_source = (ROOT / "docs" / "Tenuta_Baiamonte_System_Manual.md").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_system_manual.py").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Appendix A. Complete release coverage: 1.6.0-1.6.42", manual_source)
        self.assertIn("{{RELEASE_HISTORY_1_6}}", manual_source)
        self.assertIn("complete_release_history", builder)
        releases = [line.removeprefix("## ") for line in changelog.splitlines() if line.startswith("## 1.6.")]
        self.assertEqual(releases[0], "1.6.42")
        self.assertEqual(releases[-1], "1.6.0")
        self.assertEqual(len(releases), 42)

    def test_fresh_authorized_session_starts_on_operations_today(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("routeMap={'admin-labor':'admin-labor','admin-docs':'admin-docs'", javascript)
        self.assertIn("||'today'", javascript)
        self.assertIn("setNavMode('operations')", javascript)
        self.assertIn("setNavMode(moduleForView(view))", javascript)
        self.assertNotIn("localStorage.getItem('baiamonte-nav-mode')", javascript)


if __name__ == "__main__":
    unittest.main()
