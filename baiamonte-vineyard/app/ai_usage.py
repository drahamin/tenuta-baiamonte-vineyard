from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .db import fetch_all, fetch_one, transaction
from .service import estate_id, json_ready


# USD per one million tokens. These are a pricing snapshot used only for
# transparent estimates; each event stores the rates used at the time.
MODEL_PRICING: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "gpt-5.6-sol": (Decimal("5.00"), Decimal("0.50"), Decimal("30.00")),
    "gpt-5.6-terra": (Decimal("2.50"), Decimal("0.25"), Decimal("15.00")),
    "gpt-5.6-luna": (Decimal("1.00"), Decimal("0.10"), Decimal("6.00")),
}
DEFAULT_PRICING = MODEL_PRICING["gpt-5.6-sol"]


def _rates(model: str) -> tuple[Decimal, Decimal, Decimal]:
    return MODEL_PRICING.get(model, DEFAULT_PRICING)


def record_ai_usage(feature_code: str, result: dict[str, Any], source_record_id: str | None = None) -> None:
    """Persist API-reported token usage without ever failing the AI request."""
    try:
        usage = result.get("usage") or {}
        input_tokens = max(0, int(usage.get("input_tokens") or 0))
        output_tokens = max(0, int(usage.get("output_tokens") or 0))
        details = usage.get("input_tokens_details") or {}
        cached = max(0, min(input_tokens, int(details.get("cached_tokens") or usage.get("input_cached_tokens") or 0)))
        total = max(input_tokens + output_tokens, int(usage.get("total_tokens") or 0))
        model = str(result.get("model") or "unknown")[:120]
        input_rate, cached_rate, output_rate = _rates(model)
        cost = (
            Decimal(input_tokens - cached) * input_rate
            + Decimal(cached) * cached_rate
            + Decimal(output_tokens) * output_rate
        ) / Decimal(1_000_000)
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO ai_usage_events (estate_id,feature_code,source_record_id,model,input_tokens,cached_input_tokens,output_tokens,total_tokens,input_usd_per_million,cached_input_usd_per_million,output_usd_per_million,estimated_cost_usd,request_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), feature_code[:80], (source_record_id or "")[:255] or None, model, input_tokens, cached, output_tokens, total, input_rate, cached_rate, output_rate, cost, str(result.get("id") or "")[:160] or None),
            )
    except Exception:
        # Cost accounting must not turn a successful vineyard analysis into a
        # failed request. The admin page will make missing coverage visible.
        return


def save_ai_cost_settings(monthly_budget_usd: float, warning_percent: float, updated_by: str) -> dict[str, Any]:
    budget = max(0.0, min(float(monthly_budget_usd), 100_000.0))
    warning = max(1.0, min(float(warning_percent), 100.0))
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO ai_cost_settings (estate_id,monthly_budget_usd,warning_percent,updated_by) VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE monthly_budget_usd=VALUES(monthly_budget_usd),warning_percent=VALUES(warning_percent),updated_by=VALUES(updated_by)",
            (estate_id(), budget, warning, updated_by[:190]),
        )
    return ai_cost_summary()


def ai_cost_summary(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    month_start = datetime(now.year, now.month, 1)
    next_month = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1)
    previous_start = datetime(month_start.year - (1 if month_start.month == 1 else 0), 12 if month_start.month == 1 else month_start.month - 1, 1)
    settings = fetch_one("SELECT * FROM ai_cost_settings WHERE estate_id=%s", (estate_id(),)) or {
        "monthly_budget_usd": Decimal("25.00"), "warning_percent": Decimal("80.00"), "updated_at": None, "updated_by": None,
    }
    totals = fetch_one(
        "SELECT COUNT(*) requests,COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(cached_input_tokens),0) cached_input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,COALESCE(SUM(total_tokens),0) total_tokens,COALESCE(SUM(estimated_cost_usd),0) estimated_cost_usd,MAX(occurred_at) last_request_at "
        "FROM ai_usage_events WHERE estate_id=%s AND occurred_at >= %s AND occurred_at < %s",
        (estate_id(), month_start, next_month),
    ) or {}
    previous = fetch_one(
        "SELECT COUNT(*) requests,COALESCE(SUM(estimated_cost_usd),0) estimated_cost_usd FROM ai_usage_events WHERE estate_id=%s AND occurred_at >= %s AND occurred_at < %s",
        (estate_id(), previous_start, month_start),
    ) or {}
    by_feature = fetch_all(
        "SELECT feature_code,COUNT(*) requests,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(estimated_cost_usd) estimated_cost_usd,MAX(occurred_at) last_request_at "
        "FROM ai_usage_events WHERE estate_id=%s AND occurred_at >= %s AND occurred_at < %s GROUP BY feature_code ORDER BY estimated_cost_usd DESC",
        (estate_id(), month_start, next_month),
    )
    daily = fetch_all(
        "SELECT DATE(occurred_at) usage_date,COUNT(*) requests,SUM(estimated_cost_usd) estimated_cost_usd FROM ai_usage_events WHERE estate_id=%s AND occurred_at >= DATE_SUB(%s,INTERVAL 30 DAY) GROUP BY DATE(occurred_at) ORDER BY usage_date",
        (estate_id(), now),
    )
    cost = float(totals.get("estimated_cost_usd") or 0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    projected = cost / max(1, now.day) * days_in_month
    budget = float(settings.get("monthly_budget_usd") or 0)
    warning = float(settings.get("warning_percent") or 80)
    budget_pct = (projected / budget * 100) if budget > 0 else None
    if budget_pct is None:
        health = "unlimited"
    elif budget_pct >= 100:
        health = "over"
    elif budget_pct >= warning:
        health = "warning"
    else:
        health = "healthy"
    model_rows = fetch_all(
        "SELECT model,MAX(input_usd_per_million) input_usd_per_million,MAX(cached_input_usd_per_million) cached_input_usd_per_million,MAX(output_usd_per_million) output_usd_per_million,COUNT(*) requests FROM ai_usage_events WHERE estate_id=%s AND occurred_at >= %s AND occurred_at < %s GROUP BY model ORDER BY requests DESC",
        (estate_id(), month_start, next_month),
    )
    tracked = fetch_one("SELECT MIN(occurred_at) tracked_since FROM ai_usage_events WHERE estate_id=%s", (estate_id(),)) or {}
    return json_ready({
        "period": month_start.strftime("%Y-%m"), "tracked_since": tracked.get("tracked_since"),
        "month": totals, "previous_month": previous, "projected_month_usd": round(projected, 4),
        "budget": {"monthly_usd": budget, "warning_percent": warning, "projected_percent": round(budget_pct, 1) if budget_pct is not None else None, "health": health, "updated_at": settings.get("updated_at"), "updated_by": settings.get("updated_by")},
        "by_feature": by_feature, "daily": daily, "models": model_rows,
        "scope_note": "Vineyard Operations OpenAI API calls only. ChatGPT and Codex subscription usage is separate.",
        "pricing_note": "Estimated from API-reported tokens using the price snapshot stored with each request.",
    })
