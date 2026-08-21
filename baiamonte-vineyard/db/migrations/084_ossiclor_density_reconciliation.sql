-- Manufacturer-supported density reconciliation for OSSICLOR 20 FLOW.
-- The published range is 1.35-1.45 kg/L. Baiamonte uses the 1.40 kg/L
-- midpoint for ledger conversion while retaining the range as uncertainty.

ALTER TABLE treatment_product_profiles
  ADD COLUMN IF NOT EXISTS density_min_kg_l DECIMAL(10,5) NULL AFTER density_kg_l,
  ADD COLUMN IF NOT EXISTS density_max_kg_l DECIMAL(10,5) NULL AFTER density_min_kg_l;

UPDATE treatment_product_profiles r
JOIN products p ON p.id=r.product_id
SET r.density_kg_l=1.40000,
    r.density_min_kg_l=1.35000,
    r.density_max_kg_l=1.45000,
    r.density_source='Manufacturer sheet: 1.35-1.45 kg/L; operational midpoint 1.40 kg/L, confirmed 2026-08-21',
    r.source_summary=CONCAT_WS(' ',r.source_summary,
      'Manufacturer density range is 1.35-1.45 kg/L. Baiamonte ledger conversions use the 1.40 kg/L midpoint and retain the range as uncertainty.')
WHERE p.name='OSSICLOR 20 BLU FLOW' AND r.active=1;

INSERT INTO treatment_product_evidence
  (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'manufacturer_label','manufacturer-density:ossiclor-20-flow:2026-08-21',
  'Manufacturer sheet provided/confirmed by owner on 2026-08-21; source file pending archive',
  'SC liquid','2026-08-21','verified',
  'Manufacturer sheet density range 1.35-1.45 kg/L. Operational inventory conversion uses midpoint 1.40 kg/L; the range is retained and must not be represented as an exact lot measurement.'
FROM products p WHERE p.name='OSSICLOR 20 BLU FLOW'
ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),evidence_date=VALUES(evidence_date),
  verification_status='verified',notes=VALUES(notes);

-- Repair any existing use movement for the completed application item.
-- 2,000 g / 1.40 kg/L = 1.428571 L, posted to the 0.001 L ledger precision.
UPDATE inventory_movements m
JOIN spray_application_items i ON m.reference_type='spray_application_item' AND m.reference_id=i.id
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET m.quantity_delta=-ROUND((i.total_used/1000)/1.40000,3),
    m.notes=CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,
      ' · source total ',i.total_used,' g · converted at 1.40 kg/L operational midpoint ',
      '(manufacturer range 1.35-1.45 kg/L). [DENSITY RECONCILED 2026-08-21]')
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.status IN ('completed','applied') AND p.name='OSSICLOR 20 BLU FLOW'
  AND i.total_used IS NOT NULL AND LOWER(i.dose_unit) LIKE 'g/%';

INSERT INTO inventory_movements
  (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes)
SELECT UUID(),a.estate_id,p.id,a.application_date,'use',-ROUND((i.total_used/1000)/1.40000,3),
  'spray_application_item',i.id,
  CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,
    ' · source total ',i.total_used,' g · converted at 1.40 kg/L operational midpoint ',
    '(manufacturer range 1.35-1.45 kg/L). [DENSITY RECONCILED 2026-08-21]')
FROM spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
LEFT JOIN inventory_movements m ON m.estate_id=a.estate_id
  AND m.reference_type='spray_application_item' AND m.reference_id=i.id
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND a.status IN ('completed','applied') AND p.name='OSSICLOR 20 BLU FLOW'
  AND i.total_used IS NOT NULL AND LOWER(i.dose_unit) LIKE 'g/%' AND m.id IS NULL;
