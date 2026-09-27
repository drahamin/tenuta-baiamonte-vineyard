-- Owner-confirmed products used in the 2026 Grenache.
-- Reconcile Wendy's provisional 180-quantity yeast record with the confirmed
-- D20 identity. The source never supplied the unit, so it remains NULL.

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.additive_name='EnartisFerm D20',a.additive_type='yeast',
    a.event_status='applied',a.applied_at='2026-09-10 00:00:00',a.scheduled_at=NULL,
    a.quantity=180.0000,a.unit=NULL,a.product_lot=NULL,
    a.reason_text='Owner-confirmed EnartisFerm D20 was the yeast in Wendy''s Grenache inoculation record. The recorded quantity is 180, but its unit was not supplied and is not inferred. Preparation: 5 L water plus one spoon sugar; cool/temper the yeast mixture to the 25 C must temperature, add into a hole on each side and cover the must. Exact application time and product lot remain pending.',
    a.approved_by='David Rahamin',a.approved_at='2026-09-27 00:00:00',a.recorded_by='Owner confirmation 2026-09-27'
WHERE a.id='15500000-0000-4000-8000-000000000042';

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18400000-0000-4000-8000-000000000001',s.estate_id,w.id,'EnartisTan Rouge','tannin','applied',
       '2026-09-10 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed EnartisTan ROUGE was used in the 2026 Grenache must. The photograph confirms product identity; applied quantity, product lot and exact application time remain pending and are not inferred from the package.',
       'David Rahamin','2026-09-27 00:00:00','Owner confirmation 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18400000-0000-4000-8000-000000000002',s.estate_id,w.id,'NUTRIFERM AROM PLUS','nutrient','applied',
       '2026-09-10 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed NUTRIFERM AROM PLUS was used in the 2026 Grenache during beginning fermentation. The photograph confirms product identity; applied quantity, product lot and exact application time remain pending and are not inferred from the 1 kg package.',
       'David Rahamin','2026-09-27 00:00:00','Owner confirmation 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18400000-0000-4000-8000-000000000003',s.estate_id,s.id,w.id,'2026-09-10 00:00:00','Yeast inoculation',180.0000,NULL,
       'EnartisFerm D20. Source records quantity 180 without a unit. Prepared in 5 L water with one spoon sugar and tempered to 25 C; exact time and product lot pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18400000-0000-4000-8000-000000000004',s.estate_id,s.id,w.id,'2026-09-10 00:00:00','Tannin addition',NULL,NULL,
       'EnartisTan ROUGE confirmed used in Grenache must; quantity, product lot and exact time pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18400000-0000-4000-8000-000000000005',s.estate_id,s.id,w.id,'2026-09-10 00:00:00','Nutrient addition',NULL,NULL,
       'NUTRIFERM AROM PLUS confirmed used at beginning fermentation; quantity, product lot and exact time pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.notes=CONCAT_WS(' ',NULLIF(st.notes,''),'Owner confirmed this product was used in the 2026 Grenache; remaining stock is not inferred.'),
    st.quantity_status='unverified'
WHERE p.normalized_name IN ('enartisferm d20','enartistan rouge','nutriferm arom plus')
  AND st.notes NOT LIKE '%used in the 2026 Grenache%';

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'10 September 2026: EnartisFerm D20 (recorded quantity 180; unit pending), EnartisTan ROUGE (quantity pending) and NUTRIFERM AROM PLUS (quantity pending) confirmed used. Exact product lots and application times remain pending.')
WHERE w.estate_id=s.estate_id AND w.code='GRN-2026-01'
  AND w.notes NOT LIKE '%EnartisFerm D20 (recorded quantity 180; unit pending)%';

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '18400000-0000-4000-8000-000000000006',s.estate_id,'2026-09-27 00:00:00','Products used in 2026 Grenache',
       'Owner-confirmed product set: EnartisFerm D20, EnartisTan ROUGE and NUTRIFERM AROM PLUS. Wendy''s source record supplies yeast quantity 180 but no unit, so the unit remains pending. Tannin and nutrient quantities, all product lots and exact application times remain pending. Photographs establish product identity, not quantity or remaining stock.',
       JSON_ARRAY('owner-confirmed','grenache','red-wine','enology','products-used','2026'),'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-184','confirm_grenache_products_used','wine_lot','GRN-2026-01',
       JSON_OBJECT('products',JSON_ARRAY(
           JSON_OBJECT('name','EnartisFerm D20','quantity',180,'unit',NULL),
           JSON_OBJECT('name','EnartisTan ROUGE','quantity',NULL),
           JSON_OBJECT('name','NUTRIFERM AROM PLUS','quantity',NULL)
       ),'pending',JSON_ARRAY('D20 quantity unit','tannin quantity','nutrient quantity','product lots','exact application times'))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-184' AND a.action='confirm_grenache_products_used'
);
