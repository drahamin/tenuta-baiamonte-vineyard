from email import policy
from email.parser import BytesParser
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import intelligence
from app.domains.alerts_intake_routes import _lab_payloads, _lab_suggestions
from app.domains.laboratory_routes import lab_workflow_area
from app.mailbox import gmail_attachment_parts


FORWARDED_LAB = b"""MIME-Version: 1.0\r
From: David Rahamin <david@rahamins.com>\r
To: estate@example.com\r
Subject: Fwd: 03/09/2026\r
Content-Type: multipart/alternative; boundary=outer\r
\r
--outer\r
Content-Type: text/plain; charset=utf-8\r
\r
Forwarded laboratory report\r
--outer\r
Content-Type: multipart/mixed; boundary=inner\r
\r
--inner\r
Content-Type: text/html; charset=utf-8\r
\r
<p>Forwarded laboratory report</p>\r
--inner\r
Content-Type: application/pdf\r
Content-Disposition: inline; filename="Baiamonte 03-09-2026.pdf"\r
Content-Transfer-Encoding: base64\r
\r
JVBERi0xLjQK\r
--inner--\r
--outer--\r
"""


def test_nested_inline_forwarded_pdf_is_an_attachment() -> None:
    message = BytesParser(policy=policy.default).parsebytes(FORWARDED_LAB)
    attachments = gmail_attachment_parts(message)
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "Baiamonte 03-09-2026.pdf"
    assert attachments[0].get_content_type() == "application/pdf"


def test_owner_estate_mailbox_and_active_staff_are_trusted() -> None:
    settings = SimpleNamespace(
        gmail_allowed_senders="laboratorio@cimalab.it",
        gmail_address="estate@example.com",
    )
    with patch.object(intelligence, "fetch_all", return_value=[{"email": "Staff Member <staff@example.com>"}]):
        trusted = intelligence._trusted_gmail_senders(settings)
    assert trusted == {
        "laboratorio@cimalab.it",
        "david@rahamins.com",
        "estate@example.com",
        "staff@example.com",
    }


def test_lab_extraction_requires_api_ready_sample_types() -> None:
    source = inspect.getsource(intelligence.analyze_intake)
    assert "Normalize sample_type to exactly one API value" in source
    assert "Italian UVA/uve means grape" in source


def test_report_approval_splits_results_that_name_distinct_samples() -> None:
    extracted = {"suggested_database_records": [{
        "destination_section": "laboratory",
        "fields": {
            "lab_date": "2026-09-04",
            "sample_type": "grape",
            "results": [
                {"sample_name": "Grecanico", "analyte_code": "babo", "analyte_name": "Babo", "numeric_value": 17},
                {"sample_name": "Nerello Mascalese", "analyte_code": "babo", "analyte_name": "Babo", "numeric_value": 18},
            ],
        },
    }]}
    records = _lab_suggestions(extracted)
    assert [record["sample_name"] for record in records] == ["Grecanico", "Nerello Mascalese"]
    assert all(len(record["results"]) == 1 for record in records)


def test_laboratory_evidence_routes_by_harvest_stage() -> None:
    assert lab_workflow_area("grape")["code"] == "agronomy"
    assert lab_workflow_area("must")["code"] == "enology"
    assert lab_workflow_area("wine")["code"] == "enology"


def test_frontend_offers_one_complete_report_approval() -> None:
    source = (Path(__file__).parents[1] / "app" / "static" / "assets" / "intake-review.js").read_text(encoding="utf-8")
    assert "Approve full report" in source
    assert "approve-lab-report" in source
    assert "The forwarded email arrived without its PDF" in source
    assert "source-file" in source
    assert "Attach and analyze report" in source
    assert "data-lab-approval-error" in source


def test_report_approval_resolves_mixed_campaign_vintage_by_sample_stage() -> None:
    item = {"extracted_data": {"suggested_database_records": [{
        "destination_section": "laboratory",
        "fields": {"sample_name": "Grenache", "sample_type": "grape", "lab_date": "2026-09-07", "vintage_year": "2025/26", "results": [{"analyte_code": "apa", "analyte_name": "APA", "numeric_value": 168.4, "unit": "mg/L"}]},
    }, {
        "destination_section": "laboratory",
        "fields": {"sample_name": "Grenache 2025", "sample_type": "wine", "lab_date": "2026-09-07", "vintage_year": "2025/26", "results": [{"analyte_code": "apa", "analyte_name": "APA", "numeric_value": 101, "unit": "mg/L"}]},
    }]}}
    with patch("app.domains.alerts_intake_routes.fetch_all", return_value=[{"id": "grenache-id", "name": "Grenache"}]):
        grape, wine = _lab_payloads(item)
    assert grape.vintage_year == 2026
    assert "2025/26" in grape.vintage_assignment_evidence
    assert wine.vintage_year == 2025


def test_enology_has_a_dedicated_yan_evidence_dashboard() -> None:
    root = Path(__file__).parents[1]
    html = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "assets" / "enology-process.js").read_text(encoding="utf-8")
    assert 'id="enologyYanDashboard"' in html
    assert "function renderEnologyYan(data)" in script
    assert "Working target" in script
    assert "source_document" in script
    assert "onPointClick:openLabChartEvidence" in script


def test_lab_detail_uses_the_attachment_media_type_column() -> None:
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "media_type AS mime_type FROM entity_attachments" in source
    assert "original_filename,mime_type FROM entity_attachments" not in source
