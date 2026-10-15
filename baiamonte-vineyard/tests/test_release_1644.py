from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_security_reviews_retry_gateway_failures_without_double_counting() -> None:
    backend = (ROOT / "app/domains/security.py").read_text()
    frontend = (ROOT / "app/static/assets/security.js").read_text()

    assert "confirmed_observations=confirmed_observations+%s" in backend
    assert '0 if current.get("review_status") == "confirmed" else 1' in backend
    assert "Request failed \\((502|503|504)\\)" in frontend
    assert "saveSecurityReview" in frontend


def test_known_routine_findings_do_not_fill_the_review_queue() -> None:
    backend = (ROOT / "app/domains/security.py").read_text()

    assert "_review_status_for_finding" in backend
    assert 'confidence_pct >= 90' in backend
    assert 'review_status,reviewed_by,reviewed_at' in backend
    assert 'version: "1.10.71"' in (ROOT / "config.yaml").read_text()
