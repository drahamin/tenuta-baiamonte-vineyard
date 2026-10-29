ALTER TABLE olive_cost_models
  MODIFY press_rate_eur_per_kg DECIMAL(10,4) NULL DEFAULT NULL,
  MODIFY bottle_count DECIMAL(12,2) NULL DEFAULT NULL,
  MODIFY bottle_unit_cost_eur DECIMAL(10,4) NULL DEFAULT NULL,
  MODIFY supplier_net_eur DECIMAL(12,2) NULL DEFAULT NULL,
  MODIFY annual_labor_eur DECIMAL(12,2) NULL DEFAULT NULL,
  MODIFY harvest_labor_eur DECIMAL(12,2) NULL DEFAULT NULL,
  MODIFY harvest_rate_eur_per_tree DECIMAL(10,4) NULL DEFAULT NULL,
  ADD COLUMN cost_model_version VARCHAR(40) NOT NULL DEFAULT 'legacy_v1' AFTER record_year,
  ADD COLUMN harvest_labor_hours DECIMAL(12,2) NULL AFTER harvest_labor_eur,
  ADD COLUMN labor_hourly_rate_eur DECIMAL(10,4) NULL AFTER harvest_labor_hours,
  ADD COLUMN mill_cost_eur DECIMAL(12,2) NULL AFTER press_rate_eur_per_kg,
  ADD COLUMN transport_cost_eur DECIMAL(12,2) NULL AFTER mill_cost_eur,
  ADD COLUMN filtering_cost_eur DECIMAL(12,2) NULL AFTER transport_cost_eur,
  ADD COLUMN equipment_allocation_eur DECIMAL(12,2) NULL AFTER filtering_cost_eur,
  ADD COLUMN package_500ml_count DECIMAL(12,2) NULL AFTER bottle_unit_cost_eur,
  ADD COLUMN package_500ml_unit_cost_eur DECIMAL(10,4) NULL AFTER package_500ml_count,
  ADD COLUMN package_3l_count DECIMAL(12,2) NULL AFTER package_500ml_unit_cost_eur,
  ADD COLUMN package_3l_unit_cost_eur DECIMAL(10,4) NULL AFTER package_3l_count,
  ADD COLUMN packaging_other_eur DECIMAL(12,2) NULL AFTER package_3l_unit_cost_eur,
  ADD COLUMN analysis_storage_eur DECIMAL(12,2) NULL AFTER packaging_other_eur,
  ADD COLUMN other_cost_eur DECIMAL(12,2) NULL AFTER analysis_storage_eur,
  ADD COLUMN reconciliation_status ENUM('draft','partial','reconciled') NOT NULL DEFAULT 'draft' AFTER other_cost_eur,
  ADD COLUMN source_as_of DATE NULL AFTER reconciliation_status;

-- The 2026 harvest and oil quantities are held in olive_records. This row only
-- structures the owner's confirmed packaging plan; unknown costs remain NULL.
INSERT INTO olive_cost_models (
  id,estate_id,record_year,cost_model_version,bottle_volume_ml,bottle_count,
  package_500ml_count,package_3l_count,reconciliation_status,source_as_of,
  notes,updated_by
)
SELECT UUID(),e.id,2026,'workflow_v2',500,118,118,10,'partial','2026-10-29',
  'Recorded production outcome: 695 kg olives and approximately 89.5 L oil. Packaging is a proposed allocation of 118 x 500 ml bottles and 10 x 3 L cans; unit costs, actual packaged quantities, harvest labor, mill invoice, transport and filtration costs remain to be recorded.',
  'owner-confirmed olive outcome 2026-10-29'
FROM estates e
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE
  cost_model_version='workflow_v2',
  bottle_volume_ml=500,
  bottle_count=COALESCE(bottle_count,118),
  package_500ml_count=COALESCE(package_500ml_count,118),
  package_3l_count=COALESCE(package_3l_count,10),
  reconciliation_status=IF(reconciliation_status='reconciled','reconciled','partial'),
  source_as_of=COALESCE(source_as_of,'2026-10-29'),
  notes=COALESCE(notes,'Recorded production outcome: 695 kg olives and approximately 89.5 L oil. Packaging is a proposed allocation of 118 x 500 ml bottles and 10 x 3 L cans; unit costs, actual packaged quantities, harvest labor, mill invoice, transport and filtration costs remain to be recorded.'),
  updated_by=VALUES(updated_by);
