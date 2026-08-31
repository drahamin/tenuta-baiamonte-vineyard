from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.domains.camera_ai_policy import camera_ai_policy_status


ROOT = Path(__file__).resolve().parents[1]


@patch("app.domains.camera_ai_policy._comparison_metrics")
@patch("app.domains.camera_ai_policy.fetch_all")
@patch("app.domains.camera_ai_policy._stored_policy")
def test_primary_request_cannot_bypass_shadow_period(stored, checks, metrics):
    now = datetime(2026, 8, 31, 12, 0)
    stored.return_value = {
        "shadow_enabled": True,
        "weekly_check_enabled": True,
        "primary_requested": True,
        "enabled_at": now.isoformat(),
        "primary_not_before": (now + timedelta(days=30)).isoformat(),
    }
    checks.return_value = [{"checked_at": now - timedelta(days=days)} for days in (1, 8, 15, 22)]
    metrics.return_value = {
        "comparisons": 40, "paired": 40, "agreed": 39, "agreement_pct": 97.5,
        "local_failures": 0, "local_failure_pct": 0.0, "reference_failures": 0, "latest_at": now,
    }
    result = camera_ai_policy_status(now)
    assert result["mode"] == "shadow"
    assert result["primary_requested"] is True
    assert result["primary_active"] is False
    assert result["gates"]["shadow_period_complete"] is False


@patch("app.domains.camera_ai_policy._comparison_metrics")
@patch("app.domains.camera_ai_policy.fetch_all")
@patch("app.domains.camera_ai_policy._stored_policy")
def test_local_primary_requires_every_evidence_gate(stored, checks, metrics):
    now = datetime(2026, 10, 2, 12, 0)
    stored.return_value = {
        "shadow_enabled": True,
        "weekly_check_enabled": True,
        "primary_requested": True,
        "enabled_at": datetime(2026, 8, 31, 12, 0).isoformat(),
        "primary_not_before": datetime(2026, 9, 30, 12, 0).isoformat(),
    }
    checks.return_value = [{"checked_at": now - timedelta(days=days)} for days in (1, 8, 15, 22)]
    metrics.return_value = {
        "comparisons": 50, "paired": 49, "agreed": 46, "agreement_pct": 93.9,
        "local_failures": 1, "local_failure_pct": 2.0, "reference_failures": 0, "latest_at": now,
    }
    result = camera_ai_policy_status(now)
    assert result["mode"] == "primary"
    assert result["primary_active"] is True
    assert all(result["gates"].values())
    assert "fallback" in result


def test_camera_policy_is_durable_visible_and_weekly():
    migration = (ROOT / "db/migrations/138_camera_local_ai_promotion.sql").read_text(encoding="utf-8")
    source = (ROOT / "app/domains/camera_ai_policy.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "camera_ai_comparisons" in migration
    assert "camera_ai_weekly_checks" in migration
    assert "INTERVAL 30 DAY" in migration
    assert "CHECK_INTERVAL_DAYS = 7" in source
    assert "can never be used to manufacture four" in source
    assert "cameraAiPolicyForm" in html
