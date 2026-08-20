-- Completed treatment products must flow through to authoritative stock.
-- Only exact recorded totals with a same-dimension unit conversion are posted.
-- Unknown water volumes and mass/volume conflicts remain unresolved for human review.

-- A legacy duplicate of the olive application was previously shown in the vineyard list.
-- The owner-confirmed olive record below is authoritative; retain the duplicate only as cancelled evidence.
UPDATE spray_applications
SET status='cancelled',crop_scope='olives',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[RECONCILED 2026-08-20] Superseded duplicate. The authoritative owner-confirmed record is Olive treatment 1/2026 dated 2026-05-11; this row must not reduce stock or appear as a completed vineyard treatment.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND source_application_id='TRT-2026-OLIVE-001'
  AND id<>'20260511-0000-4000-8000-000000000001';

-- GEL DI SILICE is a liquid. The supplier description's "X 5 KG" is a catalogue/unit
-- error; the owner-confirmed physical container and label establish the 5 L package.
UPDATE inventory_movements m JOIN products p ON p.id=m.product_id
SET m.quantity_delta=5,
    m.notes=CONCAT_WS(' ',REPLACE(COALESCE(m.notes,''),'Excluded from on-hand: invoice 5 kg cannot be converted safely to L without density or a physical count.',''),'[UNIT RECONCILED 2026-08-20] Owner-confirmed physical container is liquid; supplier catalogue text "X 5 KG" is recorded as a 5 L package. Lot 26271001E2.')
WHERE p.name='GEL DI SILICE' AND m.movement_type='purchase' AND m.reference_type IN ('invoice_stock','fattureincloud_stock');

UPDATE treatment_purchase_evidence pe JOIN products p ON p.id=pe.product_id
SET pe.package_unit='L',pe.quantity_unit='L',
    pe.notes=CONCAT_WS(' ',REPLACE(COALESCE(pe.notes,''),'[STOCK REVIEW] Invoice quantity is 5 kg, while this product is managed in L; excluded from on-hand stock until density or a physical count is recorded.',''),'[UNIT RECONCILED 2026-08-20] Owner-confirmed physical container is liquid; supplier catalogue text "X 5 KG" is interpreted as one 5 L package. Lot 26271001E2.')
WHERE p.name='GEL DI SILICE';

UPDATE inventory_movements m JOIN products p ON p.id=m.product_id
SET m.notes=REPLACE(m.notes,'two 5 L packages combined','two 5 kg packages combined')
WHERE p.name='RESOLVE' AND m.movement_type='purchase';

-- Re-assert the owner-supplied vineyard sheets before posting use movements. Treatment 3
-- records 500 L; the owner explicitly confirms 400 L for Treatments 2 and 4.
UPDATE spray_applications
SET water_volume_l=500,
    source_water_text='500 L',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[INVENTORY RECONCILED 2026-08-20] Owner sheet confirms 500 L across 2026-05-08 and 2026-05-09; per-100-L rates produce exact product totals.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND LOWER(TRIM(purpose))='treatment 3';

UPDATE spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET i.dose_amount=CASE p.name
      WHEN 'MICROTHIOL DISPERSS' THEN 600 WHEN 'OSSICLOR 20 BLU FLOW' THEN 400
      WHEN 'IMPULSIVE PREMIUM' THEN 450 WHEN 'REPENTE' THEN 300
      WHEN 'FRONTIERE' THEN 150 WHEN 'SACRON 45 WG' THEN 80 ELSE i.dose_amount END,
    i.dose_unit=CASE WHEN p.name IN ('REPENTE','FRONTIERE') THEN 'ml/100 L' ELSE 'g/100 L' END,
    i.total_used=CASE p.name
      WHEN 'MICROTHIOL DISPERSS' THEN 3000 WHEN 'OSSICLOR 20 BLU FLOW' THEN 2000
      WHEN 'IMPULSIVE PREMIUM' THEN 2250 WHEN 'REPENTE' THEN 1500
      WHEN 'FRONTIERE' THEN 750 WHEN 'SACRON 45 WG' THEN 400 ELSE i.total_used END,
    i.notes='Owner sheet confirms 500 L water; total is the documented per-100-L rate multiplied by five. Mass/volume conflicts remain unresolved rather than converted.'
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND LOWER(TRIM(a.purpose))='treatment 3';

UPDATE spray_applications
SET water_volume_l=400,
    source_water_text='400 L · owner confirmed 2026-08-20',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[INVENTORY RECONCILED 2026-08-20] Owner explicitly confirms 400 L applied water; exact totals are calculated from the documented per-100-L rates.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND LOWER(TRIM(purpose)) IN ('treatment 2','treatment 4');

UPDATE spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET i.total_used=CASE
      WHEN LOWER(TRIM(a.purpose))='treatment 2' THEN CASE p.name
        WHEN 'MICROTHIOL DISPERSS' THEN 1600 WHEN 'FERTICUS 18 M' THEN 1400
        WHEN 'IMPULSIVE PREMIUM' THEN 1600 WHEN 'FRONTIERE' THEN 600
        WHEN 'SACRON 45 WG' THEN 320 ELSE i.total_used END
      WHEN LOWER(TRIM(a.purpose))='treatment 4' THEN CASE p.name
        WHEN 'RESOLVE' THEN 2000 WHEN 'MICROTHIOL DISPERSS' THEN 1800
        WHEN 'OSSICLOR 35 WG' THEN 1360 WHEN 'FRONTIERE' THEN 600
        WHEN 'REPENTE' THEN 1200 WHEN 'GEL DI SILICE' THEN 1800 ELSE i.total_used END
      ELSE i.total_used END,
    i.notes='Owner confirms 400 L applied water; total is the documented per-100-L rate multiplied by four. Any mass/volume conflict remains unresolved rather than converted.'
WHERE a.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND LOWER(TRIM(a.purpose)) IN ('treatment 2','treatment 4');

UPDATE inventory_movements m
JOIN spray_application_items i ON m.reference_type='spray_application_item' AND m.reference_id=i.id
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
SET m.product_id=i.product_id,
    m.movement_date=a.application_date,
    m.movement_type='use',
    m.quantity_delta=CASE
      WHEN p.unit='kg' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used/1000,3)
      WHEN p.unit='g' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used,3)
      WHEN p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used/1000,3)
      WHEN p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used,3)
      WHEN p.unit='kg' AND i.dose_unit LIKE 'kg/%' THEN -ROUND(i.total_used,3)
      WHEN p.unit='L' AND i.dose_unit LIKE 'L/%' THEN -ROUND(i.total_used,3)
      ELSE m.quantity_delta
    END,
    m.notes=CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,' · source total ',i.total_used,' ',SUBSTRING_INDEX(i.dose_unit,'/',1),'.')
WHERE a.status IN ('completed','applied') AND i.total_used IS NOT NULL
  AND ((p.unit='kg' AND i.dose_unit LIKE 'g/%') OR (p.unit='g' AND i.dose_unit LIKE 'g/%')
    OR (p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%') OR (p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%')
    OR (p.unit='kg' AND i.dose_unit LIKE 'kg/%') OR (p.unit='L' AND i.dose_unit LIKE 'L/%'));

INSERT INTO inventory_movements
  (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes)
SELECT UUID(),a.estate_id,i.product_id,a.application_date,'use',
  CASE
    WHEN p.unit='kg' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used/1000,3)
    WHEN p.unit='g' AND i.dose_unit LIKE 'g/%' THEN -ROUND(i.total_used,3)
    WHEN p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used/1000,3)
    WHEN p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%' THEN -ROUND(i.total_used,3)
    WHEN p.unit='kg' AND i.dose_unit LIKE 'kg/%' THEN -ROUND(i.total_used,3)
    WHEN p.unit='L' AND i.dose_unit LIKE 'L/%' THEN -ROUND(i.total_used,3)
  END,
  'spray_application_item',i.id,
  CONCAT('Confirmed treatment use: ',p.name,' · application ',a.id,' · source total ',i.total_used,' ',SUBSTRING_INDEX(i.dose_unit,'/',1),'.')
FROM spray_application_items i
JOIN spray_applications a ON a.id=i.application_id
JOIN products p ON p.id=i.product_id
LEFT JOIN inventory_movements m ON m.estate_id=a.estate_id AND m.reference_type='spray_application_item' AND m.reference_id=i.id
WHERE a.status IN ('completed','applied') AND i.total_used IS NOT NULL AND m.id IS NULL
  AND ((p.unit='kg' AND i.dose_unit LIKE 'g/%') OR (p.unit='g' AND i.dose_unit LIKE 'g/%')
    OR (p.unit='L' AND LOWER(i.dose_unit) LIKE 'ml/%') OR (p.unit='ml' AND LOWER(i.dose_unit) LIKE 'ml/%')
    OR (p.unit='kg' AND i.dose_unit LIKE 'kg/%') OR (p.unit='L' AND i.dose_unit LIKE 'L/%'));

INSERT INTO app_settings (estate_id,setting_key,setting_value)
SELECT e.id,'treatment_inventory_policy',
  '{"purchase_source":"Agriplanet/Fatture in Cloud receipts","use_source":"completed spray application items","safe_conversions":["g<->kg","ml<->L"],"unknown_total_policy":"review_required","cross_dimension_policy":"density_evidence_required","purchase_advice_policy":"provisional_when_completed_use_is_unreconciled"}'
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value),updated_at=NOW(6);
