from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from ..db import fetch_all, fetch_one
from ..service import estate_id, json_ready
from .bottling import dashboard as bottling_dashboard
from .hospitality import partner_finance_summary


def dashboard_payload(year: int, payroll_summary: Callable[[int], dict[str, Any]]) -> dict[str, Any]:
    """Build the read-only finance mirror used by the UI and HA sensors."""
    actual = fetch_one(
        "SELECT COALESCE(SUM(revenue_net),0) revenue,COALESCE(SUM(cost_net),0) cost,"
        "COALESCE(SUM(output_vat),0) output_vat,COALESCE(SUM(input_vat),0) input_vat "
        "FROM v_monthly_actual_finance WHERE estate_id=%s AND fiscal_year=%s",
        (estate_id(), year),
    ) or {}
    vat_history = fetch_all(
        "SELECT fiscal_year,COALESCE(SUM(output_vat),0) output_vat,"
        "COALESCE(SUM(input_vat),0) input_vat,"
        "COALESCE(SUM(output_vat),0)-COALESCE(SUM(input_vat),0) vat_balance "
        "FROM v_monthly_actual_finance WHERE estate_id=%s AND fiscal_year<%s "
        "GROUP BY fiscal_year ORDER BY fiscal_year",
        (estate_id(), year),
    )
    selected_year_vat_balance = float(actual.get("output_vat") or 0) - float(actual.get("input_vat") or 0)
    prior_years_vat_balance = sum(float(row.get("vat_balance") or 0) for row in vat_history)
    vat_position = {
        "selected_year": year,
        "selected_year_balance": round(selected_year_vat_balance, 2),
        "prior_years_balance": round(prior_years_vat_balance, 2),
        "combined_balance": round(selected_year_vat_balance + prior_years_vat_balance, 2),
        "prior_years": vat_history,
        "basis": "Output VAT less input VAT from mirrored Fatture in Cloud documents",
        "settlement_note": "Recorded VAT payments, filed-return settlements, and external credits are not inferred",
    }
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
        "AND YEAR(document_date)=%s AND payment_status IN ('unpaid','part_paid','unknown') AND open_amount>0 "
        "ORDER BY due_date IS NULL,due_date,document_date DESC LIMIT 25",
        (estate_id(), year),
    )
    total_open_balance_rows = fetch_all(
        "SELECT document_type,COUNT(*) document_count,COALESCE(SUM(open_amount),0) open_total "
        "FROM v_finance_document_totals WHERE estate_id=%s "
        "AND YEAR(document_date)=%s "
        "AND document_type IN ('sales_invoice','purchase_invoice') "
        "AND payment_status IN ('unpaid','part_paid','unknown') AND open_amount>0 "
        "GROUP BY document_type",
        (estate_id(), year),
    )
    total_open_by_type = {str(row.get("document_type")): row for row in total_open_balance_rows}
    total_open_balances = {
        "receivable_eur": round(float((total_open_by_type.get("sales_invoice") or {}).get("open_total") or 0), 2),
        "receivable_documents": int((total_open_by_type.get("sales_invoice") or {}).get("document_count") or 0),
        "payable_eur": round(float((total_open_by_type.get("purchase_invoice") or {}).get("open_total") or 0), 2),
        "payable_documents": int((total_open_by_type.get("purchase_invoice") or {}).get("document_count") or 0),
        "scope": f"All genuinely open Fatture in Cloud documents for {year}",
    }
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
    fic_expenses_monthly = fetch_all(
        "SELECT MONTH(document_date) expense_month,COALESCE(SUM(taxable_amount),0) expense_net,"
        "COALESCE(SUM(gross_total),0) expense_gross,COUNT(*) document_count "
        "FROM financial_documents WHERE estate_id=%s AND YEAR(document_date)=%s "
        "AND document_type='purchase_invoice' AND source='fattureincloud' AND status<>'void' "
        "GROUP BY MONTH(document_date) ORDER BY expense_month",
        (estate_id(), year),
    )
    elapsed_months = max(1, date.today().month if year == date.today().year else 12)
    projection_factor = 12 / elapsed_months if year == date.today().year else 1
    bottling_plan = bottling_dashboard(year)
    winemaking_plan = bottling_plan.get("winemaking") or {}
    cellar_plan = {
        "id": winemaking_plan.get("id"),
        "provider_name": winemaking_plan.get("provider_name"),
        "planned_cost_eur": winemaking_plan.get("planned_cost_eur") or 0,
        "status": winemaking_plan.get("status"),
        "actual_winemaking_cost": winemaking_plan.get("actual_cost_eur") or 0,
        "invoice_vintage_year": winemaking_plan.get("invoice_vintage_year"),
    }
    packaging_plan = {
        "estimated_packaging_cost": bottling_plan.get("estimated_packaging_cost_eur") or 0,
        "estimated_total_cellar_cost": bottling_plan.get("estimated_total_cellar_cost_eur") or 0,
        "planned_bottles": bottling_plan.get("planned_bottles") or 0,
        "bottle_quantity_source": bottling_plan.get("bottle_quantity_source"),
        "bottle_quantity_is_projection": bool(bottling_plan.get("bottle_quantity_is_projection")),
        "bottle_quantity_note": bottling_plan.get("bottle_quantity_note"),
        "actual_bottle_equivalents": bottling_plan.get("actual_bottle_equivalents") or 0,
        "projected_bottle_equivalents": bottling_plan.get("projected_bottle_equivalents") or 0,
    }
    actual_winemaking = float(cellar_plan.get("actual_winemaking_cost") or 0)
    planned_winemaking = float(cellar_plan.get("planned_cost_eur") or 0)
    unbilled_winemaking = 0 if actual_winemaking else planned_winemaking
    payroll = payroll_summary(year)
    labor_records = fetch_all(
        "SELECT l.id,l.work_date,l.person_or_crew,l.role,l.work_performed,l.regular_hours,l.overtime_hours,"
        "COALESCE(l.labor_cost_eur,0) labor_cost_eur,COALESCE(l.other_cost_eur,0) other_cost_eur,l.payment_status,l.pay_due_date,"
        "COALESCE(p.amount_paid_eur,0) amount_paid_eur,"
        "GREATEST(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0)-COALESCE(p.amount_paid_eur,0),0) balance_due_eur "
        "FROM labor_entries l LEFT JOIN (SELECT estate_id,labor_entry_id,SUM(amount_eur) amount_paid_eur "
        "FROM labor_invoice_payments WHERE voided_at IS NULL GROUP BY estate_id,labor_entry_id) p "
        "ON p.estate_id=l.estate_id AND p.labor_entry_id=l.id "
        "WHERE l.estate_id=%s AND YEAR(l.work_date)=%s AND l.approval_status='approved' "
        "ORDER BY l.work_date DESC,l.person_or_crew,l.id LIMIT 1000",
        (estate_id(), year),
    )
    partner_commissions = partner_finance_summary(year)
    fic_payable = float(total_open_balances.get("payable_eur") or 0)
    payroll_payable = float(payroll.get("outstanding_exposure_eur") or 0)
    partner_payable = float(partner_commissions.get("summary", {}).get("outstanding_eur") or 0)
    total_open_balances.update({
        "fic_payable_eur": round(fic_payable, 2),
        "payroll_payable_eur": round(payroll_payable, 2),
        "partner_payable_eur": round(partner_payable, 2),
        "payable_eur": round(fic_payable + payroll_payable + partner_payable, 2),
        "payable_basis": "Open supplier invoices plus approved outstanding payroll and earned hospitality partner commissions",
    })
    fic_purchase_cost = float(actual.get("cost") or 0)
    fic_receivables = float(actual.get("revenue") or 0)
    labor_cost = float(payroll.get("labor_cost_ytd") or 0)
    bottle_equivalents = float(packaging_plan.get("planned_bottles") or 0)
    all_in_cost = fic_purchase_cost + labor_cost + unbilled_winemaking
    profit_loss = fic_receivables - all_in_cost
    all_in_cost_per_bottle = all_in_cost / bottle_equivalents if bottle_equivalents > 0 else None
    profit_loss_per_bottle = profit_loss / bottle_equivalents if bottle_equivalents > 0 else None
    all_in_bottle_cost = {
        "all_in_cost_eur": round(all_in_cost, 2),
        "all_in_cost_per_bottle_eur": round(all_in_cost_per_bottle, 4) if all_in_cost_per_bottle is not None else None,
        "profit_loss_eur": round(profit_loss, 2),
        "profit_loss_per_bottle_eur": round(profit_loss_per_bottle, 4) if profit_loss_per_bottle is not None else None,
        "bottle_equivalents_750ml": bottle_equivalents,
        "per_bottle_basis": "projected current-vintage output" if packaging_plan["bottle_quantity_is_projection"] else "authoritative completed output",
        "fic_purchase_cost_eur": round(fic_purchase_cost, 2),
        "fic_receivables_credit_eur": round(fic_receivables, 2),
        "labor_cost_eur": round(labor_cost, 2),
        "unbilled_winemaking_cost_eur": round(unbilled_winemaking, 2),
        "formula": "Cost = Fatture purchases + labor + unbilled winemaking; profit/loss = Fatture sales/receivables - cost",
    }
    return json_ready({
        "year": year,
        "actual": {**actual, "result": (actual.get("revenue") or 0) - (actual.get("cost") or 0)},
        "plan": plan,
        "annual": annual,
        "monthly": monthly,
        "cash": fetch_all("SELECT * FROM v_cash_balances WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "receivables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND YEAR(document_date)=%s AND document_type='sales_invoice' AND payment_status IN ('unpaid','part_paid','unknown') AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(), year)),
        "payables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND YEAR(document_date)=%s AND document_type='purchase_invoice' AND payment_status IN ('unpaid','part_paid','unknown') AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(), year)),
        "recent_documents": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND YEAR(document_date)=%s ORDER BY document_date DESC,id DESC LIMIT 200", (estate_id(), year)),
        "document_counts": document_counts,
        "fic_expenses_monthly": fic_expenses_monthly,
        "fatture_sync": checkpoint,
        "annual_history": annual_history,
        "vat_position": vat_position,
        "projection": {
            "basis_months": elapsed_months,
            "revenue": float(actual.get("revenue") or 0) * projection_factor,
            "cost": float(actual.get("cost") or 0) * projection_factor,
            "result": (float(actual.get("revenue") or 0) - float(actual.get("cost") or 0)) * projection_factor,
            "method": "Current year-to-date annualized" if projection_factor != 1 else "Actual full-year total",
            "cellar_plan_not_in_actual": unbilled_winemaking,
            "cost_including_cellar_plan": float(actual.get("cost") or 0) * projection_factor + unbilled_winemaking,
        },
        "cellar_cost_planning": {
            **cellar_plan,
            **packaging_plan,
            **all_in_bottle_cost,
            "unbilled_winemaking_cost": unbilled_winemaking,
        },
        "open_documents": open_documents,
        "total_open_balances": total_open_balances,
        "inventory": fetch_all("SELECT * FROM v_inventory_current WHERE estate_id=%s ORDER BY category_name,name", (estate_id(),)),
        "vat": fetch_one("SELECT * FROM vat_returns WHERE estate_id=%s AND fiscal_year=%s ORDER BY FIELD(filing_status,'filed','amended','forecast','draft') LIMIT 1", (estate_id(), year)),
        "funding": fetch_all("SELECT * FROM v_funding_control WHERE estate_id=%s ORDER BY FIELD(priority,'critical','high','medium','low'),deadline LIMIT 30", (estate_id(),)),
        "requirements": requirements,
        "funding_requirements": requirements,
        "capital_projects": fetch_all("SELECT code,name,site,status,budget_low,budget_high,actual_cost,decision_gate FROM capital_projects WHERE estate_id=%s ORDER BY status,name", (estate_id(),)),
        "unit_economics": fetch_one("SELECT * FROM v_vineyard_unit_economics WHERE vintage_year=%s", (year,)),
        "payroll": payroll,
        "labor_records": labor_records,
        "partner_commissions": partner_commissions,
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
