-- Forward repair for installations that already applied migration 059 and a
-- complete seed for fresh installations. Scope every authoritative value to
-- the Baiamonte estate and preserve any cost assumptions edited by the owner.
INSERT INTO olive_records (
  id,estate_id,source_record_id,record_year,record_date,activity,details,status,
  olives_harvested_kg,oil_liters,yield_pct,notes,evidence
)
SELECT
  '20240819-0000-4000-8000-000000000002',e.id,'OLIVE-2024-001',2024,NULL,
  'Harvest and milling','332 kg olives produced 40 liters of oil; 8.3 kg olives per liter.',
  'authoritative actual',332.000,40.000,12.048,
  'Owner-authoritative 2024 oil result. Earlier unknown placeholder replaced by actual quantities.',
  'Owner-confirmed in Baiamonte dashboard conversation, 2026-08-19.'
FROM estates e
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE
  olives_harvested_kg=VALUES(olives_harvested_kg),
  oil_liters=VALUES(oil_liters),
  yield_pct=VALUES(yield_pct),
  activity=VALUES(activity),
  details=VALUES(details),
  status=VALUES(status),
  notes=VALUES(notes),
  evidence=VALUES(evidence);

INSERT IGNORE INTO olive_cost_models (
  id,estate_id,record_year,press_rate_eur_per_kg,bottle_volume_ml,bottle_count,
  bottle_unit_cost_eur,supplier_net_eur,vat_rate_pct,supplier_includes_press_bottling,
  annual_labor_eur,harvest_labor_eur,harvest_included_in_annual,
  harvest_rate_eur_per_tree,notes,updated_by
)
SELECT
  '20240819-0000-4000-8000-000000000001',e.id,2024,0.20,500,220,
  2.30,751,22,1,1000,540,1,7,
  'Owner-supplied 2024 olive cost assumptions.',
  'migration-060-owner-authoritative'
FROM estates e
WHERE e.slug='tenuta-baiamonte';
