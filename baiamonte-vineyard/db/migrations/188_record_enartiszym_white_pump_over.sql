-- Owner-confirmed second product in the 27 September Grecanico pump-over.
-- The photographed calculation is 23 g x 2 = 46 g. The EnartisZym variant,
-- original package size, product lot and remaining stock are not visible.

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18800000-0000-4000-8000-000000000001',s.estate_id,w.id,'EnartisZym — exact variant pending','enzyme','applied',
       '2026-09-27 19:05:00',46.0000,'g',NULL,
       'Owner-confirmed 46 g EnartisZym addition during active fermentation in the same evening pump-over of the primary Grecanico white wine. Photograph records 23 g x 2 = 46 g. The exact EnartisZym variant, product lot, original package size and remaining stock are not visible; do not infer RS(P) or another variant.',
       'David Rahamin','2026-09-27 19:05:00','Owner update 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18800000-0000-4000-8000-000000000002',s.estate_id,s.id,w.id,'2026-09-27 19:05:00',
       'Enzyme addition during pump-over',46.000,'g','Primary Grecanico: 46 g EnartisZym added during the evening pump-over. Exact variant, product lot and original package size remain pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=NULL,st.package_unit=NULL,st.quantity_status='unverified',
    st.notes='EnartisZym container photographed with exact variant and original package size obscured. Owner confirmed 46 g used during the primary Grecanico pump-over on 2026-09-27. Product lot and remaining balance remain unknown; no specific EnartisZym variant is inferred.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartiszym exact variant pending'
  AND st.stock_key='ddt-241-2026-09-25-enartiszym-pending';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'27 September 2026 19:05: 46 g EnartisZym (exact variant pending) added during active fermentation in the primary Grecanico evening pump-over.')
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-P'
  AND COALESCE(w.notes,'') NOT LIKE '%46 g EnartisZym (exact variant pending)%';

UPDATE notes n
JOIN wine_lots w ON w.id=n.wine_lot_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET n.body=CONCAT_WS(' ',NULLIF(n.body,''),'On 27 September at 19:05, 46 g EnartisZym (exact variant pending) was also added during the evening pump-over; calculation 23 g x 2 = 46 g.')
WHERE n.id='18300000-0000-4000-8000-000000000004'
  AND COALESCE(n.body,'') NOT LIKE '%46 g EnartisZym (exact variant pending)%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-188','record_enartiszym_white_pump_over','enology_addition_event','18800000-0000-4000-8000-000000000001',
       JSON_OBJECT('wine_lot','GRC-2026-01-P','applied_at','2026-09-27 19:05:00','product','EnartisZym — exact variant pending',
                   'quantity_g',46,'operation','pump-over','calculation','23 g x 2 = 46 g',
                   'pending',JSON_ARRAY('exact variant','product lot','original package size','remaining stock'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-188' AND a.entity_id='18800000-0000-4000-8000-000000000001');
