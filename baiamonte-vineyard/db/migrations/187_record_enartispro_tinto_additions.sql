-- Owner-confirmed EnartisPro TINTO additions on the evening of 27 September.
-- Nerello quantity is the photographed operator calculation: 16.1 hL x
-- 30 g/hL = 483 g. The primary Grecanico addition was 46 g during pump-over.

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18700000-0000-4000-8000-000000000001',s.estate_id,w.id,'EnartisPro TINTO','other','applied',
       '2026-09-27 19:02:00',483.0000,'g',NULL,
       'Owner-confirmed EnartisPro TINTO addition during active Nerello fermentation. Operator calculation photographed at 19:02: 16.1 hL x 30 g/hL = 483 g. The 16.1 hL value is retained as the dosing basis and does not silently replace the approximately 1,600 L tank-volume record. Product lot remains pending.',
       'David Rahamin','2026-09-27 19:02:00','Owner update 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18700000-0000-4000-8000-000000000002',s.estate_id,w.id,'EnartisPro TINTO','other','applied',
       '2026-09-27 19:05:00',46.0000,'g',NULL,
       'Owner-confirmed 46 g EnartisPro TINTO addition to the primary Grecanico white wine during the evening pump-over. Photograph records the operator calculation 23 g x 2 = 46 g at 19:05. This is recorded as actual use; it does not change the official product suitability or manufacturer range. Product lot remains pending.',
       'David Rahamin','2026-09-27 19:05:00','Owner update 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18700000-0000-4000-8000-000000000003',s.estate_id,s.id,w.id,'2026-09-27 19:05:00',
       'Pump-over with addition',46.000,'g','Primary Grecanico: pump-over with 46 g EnartisPro TINTO. Operator calculation was 23 g x 2; product lot remains pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18700000-0000-4000-8000-000000000004',s.estate_id,s.id,w.id,'2026-09-27 19:02:00',
       'Fermentation support addition',483.000,'g','Nerello: 483 g EnartisPro TINTO. Dosing calculation 16.1 hL x 30 g/hL; product lot remains pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=0.4710,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='Original photographed pack was 1 kg. Owner confirmed 483 g applied to Nerello and 46 g applied to primary Grecanico on 2026-09-27; 471 g calculated remaining. Product lot remains pending.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartispro tinto'
  AND st.stock_key='ddt-241-2026-09-25-pro-tinto';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'27 September 2026 19:02: 483 g EnartisPro TINTO added during active fermentation; dosing basis 16.1 hL x 30 g/hL.')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01'
  AND COALESCE(w.notes,'') NOT LIKE '%483 g EnartisPro TINTO%';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'27 September 2026 19:05: pump-over with 46 g EnartisPro TINTO in the primary Grecanico white wine.')
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-P'
  AND COALESCE(w.notes,'') NOT LIKE '%pump-over with 46 g EnartisPro TINTO%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-187','record_enartispro_tinto_additions','enology_product','EnartisPro TINTO',
       JSON_OBJECT('applied_on','2026-09-27','nerello',JSON_OBJECT('wine_lot','NM-2026-01','quantity_g',483,'dosing_basis_hl',16.1,'rate_g_hl',30),
                   'grecanico_primary',JSON_OBJECT('wine_lot','GRC-2026-01-P','quantity_g',46,'operation','pump-over'),
                   'original_stock_g',1000,'total_used_g',529,'calculated_remaining_g',471,'pending',JSON_ARRAY('product lot'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-187' AND a.entity_id='EnartisPro TINTO');
