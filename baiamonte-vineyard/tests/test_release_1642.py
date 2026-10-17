from pathlib import Path

from app.fattureincloud import SOURCE_DOCUMENT_MAX_CHARS, _source_document


ROOT = Path(__file__).parents[1]


def test_long_fattureincloud_document_url_is_preserved():
    url = "https://example.invalid/document?signature=" + "a" * 900
    assert len(url) > 500
    assert _source_document({"url": url}) == url


def test_document_url_is_extracted_from_nested_payload_and_malformed_excess_is_rejected():
    assert _source_document({"attachment_url": {"download_url": "https://example.invalid/file"}}) == "https://example.invalid/file"
    assert _source_document({"url": "x" * (SOURCE_DOCUMENT_MAX_CHARS + 1)}) is None


def test_finance_source_document_schema_accepts_long_urls():
    sql = (ROOT / "db/migrations/211_expand_finance_source_document.sql").read_text()
    assert "ALTER TABLE financial_documents" in sql
    assert "source_document TEXT NULL" in sql


def test_release_1642_is_current_without_rebuilding_the_manual():
    assert "## 1.10.62" in (ROOT / "CHANGELOG.md").read_text()
    assert "MANUAL_RELEASE = \"1.10.61\"" in (ROOT / "scripts/build_system_manual.py").read_text()
