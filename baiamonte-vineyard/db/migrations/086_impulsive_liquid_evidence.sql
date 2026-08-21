-- IMPULSIVE PREMIUM F is an estate-held liquid. The physical container label
-- records vineyard/olive foliar use in L/ha; historical field sheets used
-- 400/450 per 100 L but mistakenly wrote grams. Preserve the observed numeric
-- rates while correcting their dimension to milliliters. No density is inferred.

ALTER TABLE treatment_product_evidence ADD COLUMN IF NOT EXISTS observed_rate_max DECIMAL(12,3) NULL AFTER observed_rate;
ALTER TABLE treatment_product_evidence ADD COLUMN IF NOT EXISTS source_intake_id CHAR(36) NULL AFTER source_reference;
ALTER TABLE treatment_product_evidence ADD COLUMN IF NOT EXISTS analysis_json JSON NULL AFTER notes;
CREATE INDEX IF NOT EXISTS ix_treatment_evidence_intake ON treatment_product_evidence (source_intake_id);

UPDATE products
SET unit='L',
    notes=CONCAT_WS(' · ',NULLIF(notes,''),'Owner-supplied container label confirmed IMPULSIVE PREMIUM F is liquid; fruit trees, olive and vine foliar rate is 2–3 L/ha. Mass-volume conversion remains prohibited without a verified density.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND name='IMPULSIVE PREMIUM';

UPDATE treatment_product_profiles r
JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.measure_unit='L',r.density_kg_l=NULL,r.density_source=NULL,
    r.label_verified_on='2026-08-21',r.verification_status='verified',
    r.source_summary='Physical estate container verifies IMPULSIVE PREMIUM F is liquid. Fruit trees, olive and vine foliar label range is 2–3 L/ha. Historical per-100-L field-sheet quantities are therefore recorded in ml, not g; no density is inferred.'
WHERE p.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND p.name='IMPULSIVE PREMIUM';

UPDATE spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET i.dose_unit='ml/100 L',
    i.notes=CONCAT_WS(' · ',NULLIF(i.notes,''),'[UNIT CORRECTION 2026-08-21] IMPULSIVE PREMIUM F is liquid; the owner-supplied label and statement resolve the historical sheet unit as ml/100 L, not g/100 L. Numeric rate retained; no density conversion used.')
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND p.name='IMPULSIVE PREMIUM'
  AND LOWER(i.dose_unit) LIKE 'g/%';

UPDATE spray_applications
SET source_doses=REPLACE(REPLACE(source_doses,'IMPULSIVE PREMIUM: 450 g/100 L','IMPULSIVE PREMIUM: 450 ml/100 L'),'IMPULSIVE PREMIUM: 400 g/100 L','IMPULSIVE PREMIUM: 400 ml/100 L')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND source_doses LIKE '%IMPULSIVE PREMIUM%';

INSERT INTO treatment_product_evidence
  (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,observed_rate,observed_rate_max,observed_rate_unit,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'container_label','container-label:impulsive-premium-f:lot-120751001C1:2026-08-21',
  'Owner-supplied physical container photograph','liquid · lot 120751001C1',2,3,'L/ha','2026-08-21','verified',
  'IMPULSIVE PREMIUM F physical label: liquid foliar product; fruit trees, olive and vine 2–3 L/ha from vegetative awakening throughout the crop cycle. The source does not state density, so no mass-volume conversion is permitted.'
FROM products p
WHERE p.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND p.name='IMPULSIVE PREMIUM'
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),observed_rate=VALUES(observed_rate),observed_rate_max=VALUES(observed_rate_max),observed_rate_unit=VALUES(observed_rate_unit),evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO inventory_movements
  (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes)
SELECT UUID(),a.estate_id,p.id,a.application_date,'use',-ROUND(i.total_used/1000,3),'spray_application_item',i.id,
  CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,' · source total ',i.total_used,' ml; converted to L. [UNIT CORRECTION 2026-08-21]')
FROM spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
LEFT JOIN inventory_movements m ON m.reference_type='spray_application_item' AND m.reference_id=i.id
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.status IN ('completed','applied') AND p.name='IMPULSIVE PREMIUM'
  AND i.total_used IS NOT NULL AND LOWER(i.dose_unit) LIKE 'ml/%' AND m.id IS NULL;

UPDATE inventory_movements m
JOIN spray_application_items i ON m.reference_type='spray_application_item' AND m.reference_id=i.id
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET m.quantity_delta=-ROUND(i.total_used/1000,3),
    m.notes=CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,' · source total ',i.total_used,' ml; converted to L. [UNIT CORRECTION 2026-08-21]')
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND p.name='IMPULSIVE PREMIUM' AND i.total_used IS NOT NULL AND LOWER(i.dose_unit) LIKE 'ml/%';
