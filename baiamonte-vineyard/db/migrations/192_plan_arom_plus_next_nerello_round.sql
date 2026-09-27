-- Owner-selected next Nerello nutrition round. This is a product plan, not an
-- applied dose; the amount remains dynamic from the next APA/YAN result.

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,scheduled_at,quantity,unit,product_lot,reason_text,recorded_by)
SELECT '19200000-0000-4000-8000-000000000001',s.estate_id,w.id,'NUTRIFERM AROM PLUS','nutrient','planned',
       NULL,NULL,NULL,NULL,
       '[recipe-repeat-plan] Owner selected NUTRIFERM AROM PLUS for the next Nerello nutrition round. This is a working product choice, not an applied dose; recalculate the exact amount from the new APA/YAN result, current volume and fermentation progress.',
       'Owner plan 2026-09-27'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status='planned',
  scheduled_at=NULL,applied_at=NULL,quantity=NULL,unit=NULL,product_lot=NULL,
  reason_text=VALUES(reason_text),recorded_by=VALUES(recorded_by);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=0.5200,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='One photographed 1 kg NUTRIFERM AROM PLUS pack. Owner confirmed 480 g applied to Nerello on 2026-09-26; 520 g calculated remaining. The same product is selected for the next nutrition round, with quantity pending the next APA/YAN result.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='nutriferm arom plus'
  AND st.stock_key='ddt-241-2026-09-25-nutriferm-arom-plus';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-192','plan_next_nerello_nutrition','enology_addition_event','19200000-0000-4000-8000-000000000001',
       JSON_OBJECT('wine_lot','NM-2026-01','product','NUTRIFERM AROM PLUS','status','planned',
                   'quantity',NULL,'quantity_basis','next APA/YAN plus current volume and fermentation progress',
                   'prior_applied_g',480,'original_stock_g',1000,'calculated_remaining_g',520)
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-192' AND a.action='plan_next_nerello_nutrition'
);
