CREATE TABLE IF NOT EXISTS olive_cost_models (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  record_year SMALLINT UNSIGNED NOT NULL,
  press_rate_eur_per_kg DECIMAL(10,4) NOT NULL DEFAULT 0,
  bottle_volume_ml INT UNSIGNED NOT NULL DEFAULT 500,
  bottle_count DECIMAL(12,2) NOT NULL DEFAULT 0,
  bottle_unit_cost_eur DECIMAL(10,4) NOT NULL DEFAULT 0,
  supplier_net_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  vat_rate_pct DECIMAL(7,3) NOT NULL DEFAULT 22,
  supplier_includes_press_bottling TINYINT(1) NOT NULL DEFAULT 1,
  annual_labor_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  harvest_labor_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  harvest_included_in_annual TINYINT(1) NOT NULL DEFAULT 1,
  harvest_rate_eur_per_tree DECIMAL(10,4) NOT NULL DEFAULT 0,
  notes TEXT NULL,
  updated_by VARCHAR(160) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_olive_cost_model_year (estate_id,record_year),
  CONSTRAINT fk_olive_cost_model_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE olive_records
SET olives_harvested_kg=332.000,
    oil_liters=40.000,
    yield_pct=12.048,
    activity='Harvest and milling',
    details='332 kg olives produced 40 liters of oil; 8.3 kg olives per liter.',
    status='authoritative actual',
    notes='Owner-authoritative 2024 oil result. Earlier unknown placeholder replaced by actual quantities.',
    evidence='Owner-confirmed in Baiamonte dashboard conversation, 2026-08-19.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_record_id='OLIVE-2024-001';

INSERT INTO olive_cost_models (
  id,estate_id,record_year,press_rate_eur_per_kg,bottle_volume_ml,bottle_count,
  bottle_unit_cost_eur,supplier_net_eur,vat_rate_pct,supplier_includes_press_bottling,annual_labor_eur,
  harvest_labor_eur,harvest_included_in_annual,harvest_rate_eur_per_tree,notes,updated_by
) VALUES (
  UUID(),'00000000-0000-4000-8000-000000000001',2024,0.20,500,220,
  2.30,751.00,22.00,1,1000.00,540.00,1,7.00,
  'Owner-supplied cost assumptions. Formulas calculate 220 × €2.30 = €506 and €751 + 22% VAT = €916.22. Harvest labor is included in the annual labor total unless changed.',
  'owner-authoritative'
)
ON DUPLICATE KEY UPDATE
  press_rate_eur_per_kg=VALUES(press_rate_eur_per_kg),
  bottle_volume_ml=VALUES(bottle_volume_ml),
  bottle_count=VALUES(bottle_count),
  bottle_unit_cost_eur=VALUES(bottle_unit_cost_eur),
  supplier_net_eur=VALUES(supplier_net_eur),
  vat_rate_pct=VALUES(vat_rate_pct),
  supplier_includes_press_bottling=VALUES(supplier_includes_press_bottling),
  annual_labor_eur=VALUES(annual_labor_eur),
  harvest_labor_eur=VALUES(harvest_labor_eur),
  harvest_included_in_annual=VALUES(harvest_included_in_annual),
  harvest_rate_eur_per_tree=VALUES(harvest_rate_eur_per_tree),
  notes=VALUES(notes),
  updated_by=VALUES(updated_by);
