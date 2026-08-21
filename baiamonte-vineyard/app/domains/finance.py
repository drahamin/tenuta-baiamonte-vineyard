from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from ..db import fetch_all, fetch_one
from ..service import estate_id, json_ready
from .bottling import dashboard as bottling_dashboard


def dashboard_payload(year: int, payroll_summary: Callable[[int], dict[str, Any]]) -> dict[str, Any]:
    """Build the read-only finance mirror used by the UI and HA sensors."""
    actual = fetch_one(
        "SELECT COALESCE(SUM(revenue_net),0) revenue,COALESCE(SUM(cost_net),0) cost,"
        "COALESCE(SUM(output_vat),0) output_vat,COALESCE(SUM(input_vat),0) input_vat "
        "FROM v_monthly_actual_finance WHERE estate_id=%s AND fiscal_year=%s",
        (estate_id(), year),
    ) or {}
    plan = fetch_one(
        "SELECT COALESCE(SUM(budget_revenue),0) budget_revenue,COALESCE(SUM(budget_cost),0) budget_cost,"
        "COALESCE(SUM(latest_forecast_revenue),0) forecast_revenue,COALESCE(SUM(latest_forecast_cost),0) forecast_cost "
        "FROM monthly_financial_summary WHERE estate_id=%s AND fiscal_year=%s",
        (estate_id(), year),
    ) or {}
    annual = fetch_one(
        "SELECT a.*,s.name scenario_name,s.scenario_type FROM annual_financial_summary a "
        "JOIN financial_scenarios s ON s.id=a.scenario_id WHERE a.estate_id=%s AND a.fiscal_year=%s "
        "ORDER BY (s.scenario_type='actual') DESC,s.selected DESC LIMIT 1",
        (estate_id(), year),
    ) or {}
    monthly = fetch_all(
        "SELECT * FROM v_budget_vs_actual WHERE estate_id=%s AND fiscal_year=%s ORDER BY fiscal_month",
        (estate_id(), year),
    )
    open_documents = fetch_all(
        "SELECT * FROM v_finance_document_totals WHERE estate_id=%s "
        "AND payment_status IN ('unpaid','part_paid','unknown') "
        "ORDER BY due_date IS NULL,due_date,document_date DESC LIMIT 25",
        (estate_id(),),
    )
    requirements = fetch_all(
        "SELECT id,category,requirement_name,owner_text,status,due_date,evidence_url,notes "
        "FROM funding_requirements WHERE estate_id=%s AND status NOT IN ('complete','not_applicable') "
        "ORDER BY due_date IS NULL,due_date LIMIT 25",
        (estate_id(),),
    )
    annual_history = fetch_all(
        "SELECT YEAR(document_date) finance_year,"
        "SUM(CASE WHEN document_type='sales_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) revenue,"
        "SUM(CASE WHEN document_type='purchase_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) cost,"
        "SUM(CASE WHEN document_type='delivery_note' AND status<>'void' THEN 1 ELSE 0 END) delivery_notes,"
        "SUM(CASE WHEN document_type IN ('sales_invoice','purchase_invoice','credit_note') THEN 1 ELSE 0 END) invoices "
        "FROM financial_documents WHERE estate_id=%s GROUP BY YEAR(document_date) ORDER BY finance_year",
        (estate_id(),),
    )
    checkpoint = fetch_one(
        "SELECT last_success_at,last_attempt_at,last_error,metadata FROM sync_checkpoints "
        "WHERE estate_id=%s AND integration_name='fattureincloud'",
        (estate_id(),),
    ) or {}
    document_counts = fetch_one(
        "SELECT SUM(document_type='sales_invoice') sales_invoices,"
        "SUM(document_type='purchase_invoice') purchase_invoices,"
        "SUM(document_type='delivery_note') delivery_notes,SUM(document_type='credit_note') credit_notes "
        "FROM financial_documents WHERE estate_id=%s AND YEAR(document_date)=%s",
        (estate_id(), year),
    ) or {}
    elapsed_months = max(1, date.today().month if year == date.today().year else 12)
    projection_factor = 12 / elapsed_months if year == date.today().year else 1
    cellar_plan = fetch_one(
        "SELECT w.id,w.provider_name,w.planned_cost_eur,w.status,"
        "COALESCE((SELECT fd.taxable_amount FROM financial_documents fd JOIN finance_parties fp ON fp.id=fd.party_id "
        "WHERE fd.estate_id=w.estate_id AND fd.document_type='purchase_invoice' AND YEAR(fd.document_date)=w.vintage_year "
        "AND (UPPER(REPLACE(fp.name,' ','')) LIKE '%%GAMBINOSONIA%%' OR UPPER(REPLACE(fp.name,' ','')) LIKE '%%SEBASTIANOVINCI%%') "
        "AND fd.status<>'void' ORDER BY fd.document_date DESC LIMIT 1),0) actual_winemaking_cost "
        "FROM winemaking_cost_plans w WHERE w.estate_id=%s AND w.vintage_year=%s",
        (estate_id(), year),
    ) or {}
    bottling_plan = bottling_dashboard(year)
    packaging_plan = {
        "estimated_packaging_cost": bottling_plan.get("estimated_packaging_cost_eur") or 0,
        "estimated_total_cellar_cost": bottling_plan.get("estimated_total_cellar_cost_eur") or 0,
        "planned_bottles": bottling_plan.get("planned_bottles") or 0,
    }
    actual_winemaking = float(cellar_plan.get("actual_winemaking_cost") or 0)
    planned_winemaking = float(cellar_plan.get("planned_cost_eur") or 0)
    unbilled_winemaking = 0 if actual_winemaking else planned_winemaking
    return json_ready({
        "year": year,
        "actual": {**actual, "result": (actual.get("revenue") or 0) - (actual.get("cost") or 0)},
        "plan": plan,
        "annual": annual,
        "monthly": monthly,
        "cash": fetch_all("SELECT * FROM v_cash_balances WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "receivables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND document_type='sales_invoice' AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(),)),
        "payables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND document_type='purchase_invoice' AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(),)),
        "recent_documents": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s ORDER BY document_date DESC,id DESC LIMIT 30", (estate_id(),)),
        "document_counts": document_counts,
        "fatture_sync": checkpoint,
        "annual_history": annual_history,
        "projection": {
            "basis_months": elapsed_months,
            "revenue": float(actual.get("revenue") or 0) * projection_factor,
            "cost": float(actual.get("cost") or 0) * projection_factor,
            "result": (float(actual.get("revenue") or 0) - float(actual.get("cost") or 0)) * projection_factor,
            "method": "Current year-to-date annualized" if projection_factor != 1 else "Actual full-year total",
            "cellar_plan_not_in_actual": unbilled_winemaking,
            "cost_including_cellar_plan": float(actual.get("cost") or 0) * projection_factor + unbilled_winemaking,
        },
        "cellar_cost_planning": {**cellar_plan, **packaging_plan, "unbilled_winemaking_cost": unbilled_winemaking},
        "open_documents": open_documents,
        "inventory": fetch_all("SELECT * FROM v_inventory_current WHERE estate_id=%s ORDER BY category_name,name", (estate_id(),)),
        "vat": fetch_one("SELECT * FROM vat_returns WHERE estate_id=%s AND fiscal_year=%s ORDER BY FIELD(filing_status,'filed','amended','forecast','draft') LIMIT 1", (estate_id(), year)),
        "funding": fetch_all("SELECT * FROM v_funding_control WHERE estate_id=%s ORDER BY FIELD(priority,'critical','high','medium','low'),deadline LIMIT 30", (estate_id(),)),
        "requirements": requirements,
        "funding_requirements": requirements,
        "capital_projects": fetch_all("SELECT code,name,site,status,budget_low,budget_high,actual_cost,decision_gate FROM capital_projects WHERE estate_id=%s ORDER BY status,name", (estate_id(),)),
        "unit_economics": fetch_one("SELECT * FROM v_vineyard_unit_economics WHERE vintage_year=%s", (year,)),
        "payroll": payroll_summary(year),
    })


def home_assistant_summary(finance: dict[str, Any], year: int) -> dict[str, Any]:
    """Flatten the finance mirror into stable Home Assistant sensor fields."""
    annual = finance["annual"] or {}
    actual = finance["actual"] or {}
    cash_total = sum(float(row.get("current_balance") or 0) for row in finance["cash"])
    inventory_units = sum(float(row.get("quantity_on_hand") or 0) for row in finance["inventory"])
    bottles = sum(
        float(row.get("quantity_on_hand") or 0)
        for row in finance["inventory"]
        if row.get("unit") == "bt."
    )
    open_funding = sum(
        1 for row in finance["funding"]
        if str(row.get("status", "")).lower() not in {"closed", "rejected"}
    )
    return {
        "status": "online",
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "year": year,
        "revenue": actual.get("revenue", annual.get("revenue")),
        "cost": actual.get("cost", annual.get("total_operating_costs")),
        "result": actual.get("result", annual.get("operating_result")),
        "operating_costs": actual.get("cost", annual.get("total_operating_costs")),
        "operating_result": actual.get("result", annual.get("operating_result")),
        "scenario": annual.get("scenario_name"),
        "cash_balance": cash_total,
        "inventory_units": inventory_units,
        "bottles_on_hand": bottles,
        "open_receivables": sum(float(row.get("open_amount") or 0) for row in finance["receivables"]),
        "open_payables": sum(float(row.get("open_amount") or 0) for row in finance["payables"]),
        "open_funding_opportunities": open_funding,
        "funding_actions_due": len(finance["funding_requirements"]),
        "funding_actions": len(finance["funding_requirements"]),
        "cost_per_kg": (finance["unit_economics"] or {}).get("cost_per_kg"),
        "monthly": finance["monthly"],
        "funding": finance["funding"][:12],
    }
