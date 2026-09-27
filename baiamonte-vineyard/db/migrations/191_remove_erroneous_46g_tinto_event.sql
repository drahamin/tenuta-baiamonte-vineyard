-- Owner-directed cleanup: remove the erroneous 46 g EnartisPro TINTO event
-- completely. Correct records remain: 483 g TINTO and 46 g COLOR PLUS.

DELETE FROM enology_addition_events
WHERE id='18700000-0000-4000-8000-000000000002'
  AND additive_name='EnartisPro TINTO'
  AND quantity=46.0000
  AND unit='g';

DELETE FROM cellar_operations
WHERE id='18700000-0000-4000-8000-000000000003';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=0.5170,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='Original photographed pack was 1 kg. Owner confirmed 483 g total EnartisPro TINTO applied to Nerello on 2026-09-27 (16.1 hL x 30 g/hL); 517 g calculated remaining. No 46 g TINTO event exists. Product lot remains pending.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartispro tinto'
  AND st.stock_key='ddt-241-2026-09-25-pro-tinto';

UPDATE audit_events
SET after_data=JSON_OBJECT(
      'applied_on','2026-09-27',
      'nerello',JSON_OBJECT('wine_lot','NM-2026-01','quantity_g',483,'dosing_basis_hl',16.1,'rate_g_hl',30),
      'original_stock_g',1000,'total_used_g',483,'calculated_remaining_g',517,
      'pending',JSON_ARRAY('product lot'))
WHERE actor='migration-187' AND entity_id='EnartisPro TINTO';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT e.id,'migration-191','remove_erroneous_tinto_event','enology_addition_event','18700000-0000-4000-8000-000000000002',
       JSON_OBJECT('product','EnartisPro TINTO','quantity_g',46,'status','cancelled'),
       JSON_OBJECT('deleted',TRUE,'correct_tinto_total_g',483,'color_plus_g',46,'calculated_tinto_remaining_g',517)
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-191' AND a.action='remove_erroneous_tinto_event'
);
