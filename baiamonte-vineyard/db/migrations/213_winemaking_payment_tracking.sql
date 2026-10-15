ALTER TABLE winemaking_cost_plans
  ADD COLUMN IF NOT EXISTS amount_paid_eur DECIMAL(14,2) NOT NULL DEFAULT 0 AFTER planned_cost_eur;

UPDATE winemaking_cost_plans
SET planned_cost_eur=21500.00,
    amount_paid_eur=12500.00,
    notes='Owner-confirmed 2026 winemaking service total: €21,500. Payments recorded: €4,500, €4,000, and €4,000 (€12,500 paid). Remaining balance: €9,000. Payment dates and account not supplied.',
    updated_by='owner confirmation'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2026
  AND provider_name='Sebastiano Vinci';
