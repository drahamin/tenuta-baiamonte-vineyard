-- Owner-confirmed products used in the 2026 Grecanico white wine.
-- Known quantities remain exact. Product use is recorded without inventing
-- quantities, lots, times or allocation to the small tail-fraction tank.

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.event_status='applied',a.applied_at='2026-09-11 00:00:00',a.scheduled_at=NULL,
    a.quantity=500.0000,a.unit='g',
    a.reason_text='Owner-confirmed EnartisFerm ES181 use in the primary Grecanico white must: 500 g prepared in 5 L water at 35 C, rested 20 minutes and tempered with must before inoculation. Exact application time and product lot remain pending.',
    a.approved_by='David Rahamin',a.approved_at='2026-09-27 00:00:00',a.recorded_by='Owner confirmation 2026-09-27'
WHERE a.id='15500000-0000-4000-8000-000000000041';

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18300000-0000-4000-8000-000000000001',s.estate_id,w.id,'crystalMUSTGRAPE','treatment','applied',
       '2026-09-24 00:00:00',10.0000,'kg',NULL,
       'Owner-confirmed two 5 kg bags (10 kg total) of crystalMUSTGRAPE added to the primary Grecanico white wine during active fermentation for alcohol consistency. A pump-over followed; exact addition time and product lot remain pending.',
       'David Rahamin','2026-09-27 00:00:00','Owner confirmation 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18300000-0000-4000-8000-000000000002',s.estate_id,w.id,'NUTRIFERM AROM PLUS','nutrient','applied',
       '2026-09-11 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed NUTRIFERM AROM PLUS was used in the primary Grecanico white wine at the beginning of fermentation. Exact quantity, product lot and application time remain pending; no quantity is inferred from the photographed 1 kg package.',
       'David Rahamin','2026-09-27 00:00:00','Owner confirmation 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18300000-0000-4000-8000-000000000003',s.estate_id,w.id,'EnartisPro BLANCO','other','applied',
       '2026-09-11 00:00:00',NULL,NULL,'50882',
       'Owner-confirmed EnartisPro BLANCO was used in the primary Grecanico white wine at the beginning of fermentation. Package evidence records lot 50882, expiry June 2029 and a 10-30 g/hL package range; exact applied quantity and time remain pending.',
       'David Rahamin','2026-09-27 00:00:00','Owner confirmation 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.notes=CONCAT_WS(' ',NULLIF(st.notes,''),'Owner confirmed this product was used in the 2026 Grecanico white wine; remaining stock is not inferred.'),
    st.quantity_status='unverified'
WHERE p.normalized_name IN ('enartisferm es181','nutriferm arom plus','enartispro blanco')
  AND st.notes NOT LIKE '%used in the 2026 Grecanico white wine%';

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '18300000-0000-4000-8000-000000000004',s.estate_id,'2026-09-27 00:00:00','Products used in 2026 Grecanico white wine',
       'Owner-confirmed product set: CLARIL AF (233.41 g primary and 60 g small tank), EnartisFerm ES181 (500 g primary), crystalMUSTGRAPE (10 kg primary), NUTRIFERM AROM PLUS (quantity pending) and EnartisPro BLANCO lot 50882 (quantity pending). The photographs confirm product identity and packaging; they do not establish unreported quantities or remaining stock.',
       JSON_ARRAY('owner-confirmed','grecanico','white-wine','enology','products-used','2026'),'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-183','confirm_grecanico_products_used','wine_lot','GRC-2026-01-P',
       JSON_OBJECT('products',JSON_ARRAY(
           JSON_OBJECT('name','CLARIL AF','primary_g',233.41,'small_g',60),
           JSON_OBJECT('name','EnartisFerm ES181','primary_g',500),
           JSON_OBJECT('name','crystalMUSTGRAPE','primary_kg',10),
           JSON_OBJECT('name','NUTRIFERM AROM PLUS','quantity',NULL),
           JSON_OBJECT('name','EnartisPro BLANCO','quantity',NULL,'product_lot','50882','expires_on','2029-06-30')
       ),'pending',JSON_ARRAY('AROM PLUS quantity and lot','BLANCO quantity and exact time','remaining stock counts'))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-183' AND a.action='confirm_grecanico_products_used'
);
