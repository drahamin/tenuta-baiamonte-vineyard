-- Owner-confirmed second product in the 27 September Grecanico pump-over.
-- The photographed calculation is 23 g x 2 = 46 g. Follow-up evidence identifies
-- the enzyme as EnartisZym COLOR PLUS; DDT 241 records 250 g, lot 250258701.

UPDATE enology_product_catalog
SET product_name='EnartisZym COLOR PLUS',normalized_name='enartiszym color plus',range_code='enzymes',range_name='Enzymes',
    product_class='enzyme',wine_colors='red',process_stages='must,fermentation',
    description='EnartisZym COLOR PLUS enzyme identified by the owner and Enodoro DDT 241. The supplied pack was 250 g, lot 250258701. Product-specific dosing remains unavailable until its technical data sheet is linked.',
    dose_min=NULL,dose_max=NULL,dose_unit=NULL,dose_basis='Technical data sheet still required for projection.',dose_verified=0,
    source_url='Owner identification plus Enodoro DDT 241 dated 2026-09-25',source_checked_at=NOW(6),present_in_latest=1,active=1
WHERE manufacturer='ENARTIS' AND normalized_name='color plus';

UPDATE enology_product_catalog
SET active=0,present_in_latest=0,
    description='Superseded unresolved placeholder: the photographed enzyme was identified by the owner as EnartisZym COLOR PLUS.'
WHERE manufacturer='ENARTIS' AND normalized_name='enartiszym exact variant pending';

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '18800000-0000-4000-8000-000000000001',s.estate_id,w.id,'EnartisZym COLOR PLUS','enzyme','applied',
       '2026-09-27 19:05:00',46.0000,'g','250258701',
       'Owner-confirmed 46 g EnartisZym COLOR PLUS addition during active fermentation in the same evening pump-over of the primary Grecanico white wine. Photograph records 23 g x 2 = 46 g. Follow-up evidence identifies COLOR PLUS and Enodoro DDT 241 records the supplied 250 g pack and lot 250258701.',
       'David Rahamin','2026-09-27 19:05:00','Owner update 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18800000-0000-4000-8000-000000000002',s.estate_id,s.id,w.id,'2026-09-27 19:05:00',
       'Enzyme addition during pump-over',46.000,'g','Primary Grecanico: 46 g EnartisZym COLOR PLUS, lot 250258701, added during the evening pump-over.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.product_lot='250258701',st.package_size=0.2040,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='Enodoro DDT 241 records one 250 g EnartisZym COLOR PLUS pack, lot 250258701. Owner confirmed 46 g applied during the primary Grecanico pump-over on 2026-09-27; 204 g calculated remaining.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartiszym color plus'
  AND st.stock_key='ddt-241-2026-09-25-color-plus';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.active=0,st.notes='Superseded unresolved stock placeholder: owner identified the enzyme as EnartisZym COLOR PLUS.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartiszym exact variant pending'
  AND st.stock_key='ddt-241-2026-09-25-enartiszym-pending';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'27 September 2026 19:05: 46 g EnartisZym COLOR PLUS, lot 250258701, added during active fermentation in the primary Grecanico evening pump-over.')
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-P'
  AND COALESCE(w.notes,'') NOT LIKE '%46 g EnartisZym COLOR PLUS%';

UPDATE notes n
SET n.body=CONCAT_WS(' ',NULLIF(n.body,''),'On 27 September at 19:05, 46 g EnartisZym COLOR PLUS, lot 250258701, was also added during the evening pump-over; calculation 23 g x 2 = 46 g.')
WHERE n.id='18300000-0000-4000-8000-000000000004'
  AND COALESCE(n.body,'') NOT LIKE '%46 g EnartisZym COLOR PLUS%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-188','record_enartiszym_white_pump_over','enology_addition_event','18800000-0000-4000-8000-000000000001',
       JSON_OBJECT('wine_lot','GRC-2026-01-P','applied_at','2026-09-27 19:05:00','product','EnartisZym COLOR PLUS','product_lot','250258701',
                   'quantity_g',46,'operation','pump-over','calculation','23 g x 2 = 46 g',
                   'original_stock_g',250,'calculated_remaining_g',204,'pending',JSON_ARRAY('exact application minute'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-188' AND a.entity_id='18800000-0000-4000-8000-000000000001');
