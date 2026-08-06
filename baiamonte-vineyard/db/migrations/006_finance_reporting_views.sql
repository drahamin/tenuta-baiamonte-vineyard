CREATE OR REPLACE VIEW v_finance_document_totals AS
SELECT d.id,d.estate_id,d.document_type,d.document_number,d.document_date,d.due_date,
       p.name party_name,d.taxable_amount,d.vat_amount,d.gross_total,d.payment_status,d.status,
       COALESCE(SUM(a.allocated_amount),0) allocated_cash,
       d.gross_total-COALESCE(SUM(a.allocated_amount),0) open_amount
FROM financial_documents d
LEFT JOIN finance_parties p ON p.id=d.party_id
LEFT JOIN cash_allocations a ON a.document_id=d.id
GROUP BY d.id,d.estate_id,d.document_type,d.document_number,d.document_date,d.due_date,p.name,
         d.taxable_amount,d.vat_amount,d.gross_total,d.payment_status,d.status;

CREATE OR REPLACE VIEW v_monthly_actual_finance AS
SELECT estate_id,YEAR(document_date) fiscal_year,MONTH(document_date) fiscal_month,
       SUM(CASE WHEN document_type='sales_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) revenue_net,
       SUM(CASE WHEN document_type='purchase_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) cost_net,
       SUM(CASE WHEN document_type='sales_invoice' AND status<>'void' THEN vat_amount ELSE 0 END) output_vat,
       SUM(CASE WHEN document_type='purchase_invoice' AND status<>'void' THEN vat_amount ELSE 0 END) input_vat
FROM financial_documents
GROUP BY estate_id,YEAR(document_date),MONTH(document_date);

CREATE OR REPLACE VIEW v_budget_vs_actual AS
SELECT m.estate_id,m.fiscal_year,m.fiscal_month,m.status,
       COALESCE(a.revenue_net,m.actual_revenue) actual_revenue,
       COALESCE(a.cost_net,m.actual_cost) actual_cost,
       m.budget_revenue,m.budget_cost,m.latest_forecast_revenue,m.latest_forecast_cost,
       COALESCE(a.revenue_net,m.actual_revenue,0)-COALESCE(a.cost_net,m.actual_cost,0) actual_result,
       COALESCE(a.revenue_net,m.actual_revenue,0)-COALESCE(m.budget_revenue,0) revenue_variance,
       COALESCE(a.cost_net,m.actual_cost,0)-COALESCE(m.budget_cost,0) cost_variance
FROM monthly_financial_summary m
LEFT JOIN v_monthly_actual_finance a ON a.estate_id=m.estate_id AND a.fiscal_year=m.fiscal_year AND a.fiscal_month=m.fiscal_month;

CREATE OR REPLACE VIEW v_cash_balances AS
SELECT a.id,a.estate_id,a.name,a.account_type,a.currency,
       a.opening_balance+COALESCE(SUM(t.amount_in-t.amount_out),0) current_balance,
       MAX(t.transaction_date) last_transaction_date
FROM cash_accounts a
LEFT JOIN cash_transactions t ON t.cash_account_id=a.id
WHERE a.active=1
GROUP BY a.id,a.estate_id,a.name,a.account_type,a.currency,a.opening_balance;

CREATE OR REPLACE VIEW v_inventory_current AS
SELECT s.estate_id,s.product_id,p.sku,p.name,p.category_name,p.unit,s.snapshot_date,s.quantity_on_hand,
       s.average_cost,s.average_sales_price,s.inventory_value
FROM inventory_snapshots s
JOIN products p ON p.id=s.product_id
JOIN (SELECT estate_id,product_id,MAX(snapshot_date) snapshot_date FROM inventory_snapshots GROUP BY estate_id,product_id) latest
  ON latest.estate_id=s.estate_id AND latest.product_id=s.product_id AND latest.snapshot_date=s.snapshot_date;

CREATE OR REPLACE VIEW v_funding_control AS
SELECT o.id,o.estate_id,o.source_opportunity_id,o.program_name,o.status,o.fit,o.priority,o.deadline,
       o.next_action,o.owner_text,o.last_verified,o.official_source_url,
       COUNT(DISTINCT a.id) application_count,
       COALESCE(SUM(a.requested_amount),0) requested_amount,
       COALESCE(SUM(a.approved_amount),0) approved_amount
FROM funding_opportunities o
LEFT JOIN funding_applications a ON a.opportunity_id=o.id
WHERE o.active=1
GROUP BY o.id,o.estate_id,o.source_opportunity_id,o.program_name,o.status,o.fit,o.priority,o.deadline,
         o.next_action,o.owner_text,o.last_verified,o.official_source_url;

CREATE OR REPLACE VIEW v_vineyard_unit_economics AS
SELECT s.vintage_year,
       COALESCE(h.harvest_kg,0) harvest_kg,
       COALESCE(v.wine_l,0) wine_l,
       COALESCE(inv.bottles,0) bottles_on_hand,
       COALESCE(costs.actual_cost,0) operating_cost,
       CASE WHEN h.harvest_kg>0 THEN costs.actual_cost/h.harvest_kg ELSE NULL END cost_per_kg,
       CASE WHEN v.wine_l>0 THEN costs.actual_cost/v.wine_l ELSE NULL END cost_per_liter
FROM seasons s
LEFT JOIN (SELECT season_id,SUM(weight_kg) harvest_kg FROM harvest_lots GROUP BY season_id) h ON h.season_id=s.id
LEFT JOIN (SELECT estate_id,vintage_year,SUM(wine_l) wine_l FROM vintage_summaries GROUP BY estate_id,vintage_year) v ON v.estate_id=s.estate_id AND v.vintage_year=s.vintage_year
LEFT JOIN (SELECT estate_id,SUM(quantity_on_hand) bottles FROM v_inventory_current WHERE unit='bt.' GROUP BY estate_id) inv ON inv.estate_id=s.estate_id
LEFT JOIN (SELECT estate_id,fiscal_year,SUM(actual_cost) actual_cost FROM monthly_financial_summary GROUP BY estate_id,fiscal_year) costs ON costs.estate_id=s.estate_id AND costs.fiscal_year=s.vintage_year;
