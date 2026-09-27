-- Owner correction: the EnartisPro TINTO amount used was 483 g (16.1 hL x
-- 30 g/hL). The photographed 23 g x 2 = 46 g calculation belongs only to
-- EnartisZym COLOR PLUS. Cancel the duplicate 46 g TINTO record.

UPDATE enology_addition_events
SET event_status='cancelled',applied_at=NULL,approved_at=NULL,
    reason_text='Cancelled by owner correction on 2026-09-27: the EnartisPro TINTO amount used in Nerello was 483 g total. The 23 g x 2 = 46 g calculation belongs to EnartisZym COLOR PLUS, not TINTO.',
    recorded_by='Owner correction 2026-09-27'
WHERE id='18700000-0000-4000-8000-000000000002';

DELETE FROM cellar_operations
WHERE id='18700000-0000-4000-8000-000000000003';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=REPLACE(
      COALESCE(w.notes,''),
      '27 September 2026 19:05: Nerello evening pump-over with an additional 46 g EnartisPro TINTO and 46 g EnartisZym COLOR PLUS lot 250258701; both quantities calculated as 23 g x 2.',
      '27 September 2026 19:05: Nerello evening pump-over with 46 g EnartisZym COLOR PLUS lot 250258701; quantity calculated as 23 g x 2. EnartisPro TINTO used was 483 g total, calculated as 16.1 hL x 30 g/hL.')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=0.5170,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='Original photographed pack was 1 kg. Owner confirmed 483 g total EnartisPro TINTO applied to Nerello on 2026-09-27 (16.1 hL x 30 g/hL); 517 g calculated remaining. Product lot remains pending.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartispro tinto'
  AND st.stock_key='ddt-241-2026-09-25-pro-tinto';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT e.id,'migration-190','correct_tinto_quantity','enology_addition_event','18700000-0000-4000-8000-000000000002',
       JSON_OBJECT('incorrect_extra_tinto_g',46,'incorrect_tinto_total_g',529,'calculation','23 g x 2'),
       JSON_OBJECT('correct_tinto_total_g',483,'calculation','16.1 hL x 30 g/hL',
                   'original_stock_g',1000,'calculated_remaining_g',517,
                   'color_plus_g',46,'color_plus_calculation','23 g x 2')
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-190' AND a.action='correct_tinto_quantity'
);
