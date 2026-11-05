CREATE TABLE IF NOT EXISTS enology_mlf_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  product_name VARCHAR(160) NOT NULL DEFAULT 'LALVIN VP41 MBR',
  formulation VARCHAR(40) NOT NULL DEFAULT 'MBR',
  timing_plan VARCHAR(40) NOT NULL DEFAULT 'sequential',
  volume_min_l DECIMAL(12,3) NULL,
  volume_max_l DECIMAL(12,3) NULL,
  volume_basis VARCHAR(40) NOT NULL,
  volume_basis_note VARCHAR(700) NOT NULL,
  small_sachet_coverage_l DECIMAL(12,3) NOT NULL DEFAULT 250,
  large_sachet_coverage_l DECIMAL(12,3) NOT NULL DEFAULT 2500,
  exact_label_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  suitability_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  approved_by VARCHAR(160) NULL,
  notes TEXT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_mlf_plan_lot (wine_lot_id),
  CONSTRAINT fk_enology_mlf_plan_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_enology_mlf_plan_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
);

INSERT INTO enology_mlf_plans
  (id,estate_id,wine_lot_id,volume_min_l,volume_max_l,volume_basis,volume_basis_note,notes)
SELECT UUID(),w.estate_id,w.id,1600,1600,'old_must_estimate',
       'September must estimate; not a current measured wine volume.',
       'Purchase planning only: 6.4 equivalent 250 L doses, rounded up to 7 whole small sachets if 1,600 L is confirmed current. Confirm current liters, exact VP41 MBR label and suitability with Sebastiano before dosing. Do not divide a large sachet by weight.'
FROM wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE w.code='NM-2026-01'
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),formulation=VALUES(formulation),volume_min_l=VALUES(volume_min_l),volume_max_l=VALUES(volume_max_l),volume_basis=VALUES(volume_basis),volume_basis_note=VALUES(volume_basis_note),small_sachet_coverage_l=VALUES(small_sachet_coverage_l),large_sachet_coverage_l=VALUES(large_sachet_coverage_l),notes=VALUES(notes);

INSERT INTO enology_mlf_plans
  (id,estate_id,wine_lot_id,volume_min_l,volume_max_l,volume_basis,volume_basis_note,notes)
SELECT UUID(),w.estate_id,w.id,240,300,'illustrative_yield_range',
       'Illustrative 0.60-0.75 L/kg finished-wine yield from 399.25 kg grapes; pressed wine volume was not recorded. The 450 L figure included skins and is excluded.',
       'Purchase planning only: 0.96-1.20 equivalent 250 L doses. One whole small sachet only if current wine is 250 L or less; two if above 250 L. Confirm current liters, exact VP41 MBR label and suitability with Sebastiano before dosing. Do not divide a large sachet by weight.'
FROM wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE w.code='GRN-2026-01'
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),formulation=VALUES(formulation),volume_min_l=VALUES(volume_min_l),volume_max_l=VALUES(volume_max_l),volume_basis=VALUES(volume_basis),volume_basis_note=VALUES(volume_basis_note),small_sachet_coverage_l=VALUES(small_sachet_coverage_l),large_sachet_coverage_l=VALUES(large_sachet_coverage_l),notes=VALUES(notes);

INSERT INTO enology_recipe_preferences
  (id,estate_id,season_id,plan_key,wine_lot_id,variety_name,style_intensity,style_target,mlf_intent,updated_by)
SELECT UUID(),w.estate_id,w.season_id,CONCAT('lot:',w.id),w.id,w.variety_summary,50,'balanced','allow','migration-235'
FROM wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE w.code IN ('NM-2026-01','GRN-2026-01')
ON DUPLICATE KEY UPDATE mlf_intent='allow',updated_by='migration-235';

UPDATE enology_product_catalog
SET product_name='LALVIN VP41 MBR',normalized_name='lalvin vp41 mbr',
    description='Direct-inoculation Oenococcus oeni MBR culture for malolactic fermentation. Use one complete sachet for the hL coverage printed on that exact pack; 1-STEP is a separate formulation and protocol.',
    dose_basis='Whole-sachet coverage printed on the exact MBR pack; never divide a large sachet by weight.',source_checked_at=NOW(6)
WHERE manufacturer='LALLEMAND OENOLOGY' AND normalized_name IN ('lalvin vp41','lalvin vp41 mbr');

UPDATE enology_product_protocols p JOIN enology_product_catalog c ON c.id=p.product_catalog_id
SET p.protocol_name='VP41 MBR malolactic inoculation',p.required_lab_analytes='ph,malic_acid,lactic_acid,total_so2,free_so2,actual_alcohol,residual_sugar',
    p.prerequisites='Current measured wine volume, exact MBR sachet label and coverage, selected co-inoculation or sequential timing, current temperature, MLF feasibility and Sebastiano/enologist approval',
    p.preparation='Direct inoculation is supported by the current MBR sheet. If the exact pack directs optional rehydration, use 20 times its weight of clean chlorine-free water at 20 C for no more than 15 minutes.',
    p.application_instructions='Use one complete sachet for the hL coverage printed on that exact MBR pack. Monitor malic acid every 2-4 days and stabilize only after analytical completion is confirmed.',
    p.incompatibilities='Working feasibility gates: temperature above 16 C, pH above approximately 3.1-3.2, alcohol no more than 16% vol and total SO2 no more than 60 mg/L; lower pH, alcohol above 14.5% or total SO2 above 45 mg/L need particular caution. Do not treat VP41 1-STEP as the same formulation or split a large sachet by weight.',
    p.source_revision='Lallemand VP41 MBR technical data sheets reviewed 2026-11-05',p.verified_on='2026-11-05'
WHERE c.manufacturer='LALLEMAND OENOLOGY' AND c.normalized_name='lalvin vp41 mbr' AND p.trigger_code='mlf_inoculation';
