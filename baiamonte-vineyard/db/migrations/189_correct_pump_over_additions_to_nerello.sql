-- Owner correction: both 46 g additions recorded at 19:05 on 27 September
-- belonged to the Nerello pump-over, not the primary Grecanico white wine.

UPDATE enology_addition_events a
JOIN wine_lots current_lot ON current_lot.id=a.wine_lot_id
JOIN seasons s ON s.id=current_lot.season_id AND s.vintage_year=2026
JOIN wine_lots target_lot ON target_lot.season_id=s.id AND target_lot.code='NM-2026-01'
SET a.wine_lot_id=target_lot.id,
    a.reason_text='Owner-corrected assignment: 46 g EnartisPro TINTO was added during the 27 September evening pump-over of the Nerello, not the white wine. Photograph records the operator calculation 23 g x 2 = 46 g at 19:05. This was an additional TINTO application after the separately recorded 483 g Nerello addition; product lot remains pending.',
    a.recorded_by='Owner correction 2026-09-27'
WHERE a.id='18700000-0000-4000-8000-000000000002';

UPDATE enology_addition_events a
JOIN wine_lots current_lot ON current_lot.id=a.wine_lot_id
JOIN seasons s ON s.id=current_lot.season_id AND s.vintage_year=2026
JOIN wine_lots target_lot ON target_lot.season_id=s.id AND target_lot.code='NM-2026-01'
SET a.wine_lot_id=target_lot.id,
    a.reason_text='Owner-corrected assignment: 46 g EnartisZym COLOR PLUS, lot 250258701, was added during active fermentation in the 27 September evening pump-over of the Nerello, not the white wine. Photograph records 23 g x 2 = 46 g.',
    a.recorded_by='Owner correction 2026-09-27'
WHERE a.id='18800000-0000-4000-8000-000000000001';

UPDATE cellar_operations op
JOIN wine_lots current_lot ON current_lot.id=op.wine_lot_id
JOIN seasons s ON s.id=current_lot.season_id AND s.vintage_year=2026
JOIN wine_lots target_lot ON target_lot.season_id=s.id AND target_lot.code='NM-2026-01'
SET op.wine_lot_id=target_lot.id,
    op.notes='Nerello: evening pump-over with an additional 46 g EnartisPro TINTO. Operator calculation was 23 g x 2; product lot remains pending.'
WHERE op.id='18700000-0000-4000-8000-000000000003';

UPDATE cellar_operations op
JOIN wine_lots current_lot ON current_lot.id=op.wine_lot_id
JOIN seasons s ON s.id=current_lot.season_id AND s.vintage_year=2026
JOIN wine_lots target_lot ON target_lot.season_id=s.id AND target_lot.code='NM-2026-01'
SET op.wine_lot_id=target_lot.id,
    op.notes='Nerello: 46 g EnartisZym COLOR PLUS, lot 250258701, added during the evening pump-over.'
WHERE op.id='18800000-0000-4000-8000-000000000002';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=TRIM(BOTH '\n' FROM REPLACE(REPLACE(
      COALESCE(w.notes,''),
      '27 September 2026 19:05: pump-over with 46 g EnartisPro TINTO in the primary Grecanico white wine.',''),
      '27 September 2026 19:05: 46 g EnartisZym COLOR PLUS, lot 250258701, added during active fermentation in the primary Grecanico evening pump-over.',''))
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-P';

UPDATE notes
SET body=TRIM(REPLACE(
      body,
      'On 27 September at 19:05, 46 g EnartisZym COLOR PLUS, lot 250258701, was also added during the evening pump-over; calculation 23 g x 2 = 46 g.',''))
WHERE id='18300000-0000-4000-8000-000000000004';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'27 September 2026 19:05: Nerello evening pump-over with an additional 46 g EnartisPro TINTO and 46 g EnartisZym COLOR PLUS lot 250258701; both quantities calculated as 23 g x 2.')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01'
  AND COALESCE(w.notes,'') NOT LIKE '%Nerello evening pump-over with an additional 46 g EnartisPro TINTO%';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.notes='Original photographed pack was 1 kg. Owner confirmed 483 g plus an additional 46 g applied to Nerello on 2026-09-27; 471 g calculated remaining. Product lot remains pending.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartispro tinto'
  AND st.stock_key='ddt-241-2026-09-25-pro-tinto';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.notes='Enodoro DDT 241 records one 250 g EnartisZym COLOR PLUS pack, lot 250258701. Owner confirmed 46 g applied during the Nerello pump-over on 2026-09-27; 204 g calculated remaining.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartiszym color plus'
  AND st.stock_key='ddt-241-2026-09-25-color-plus';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT e.id,'migration-189','correct_pump_over_lot_assignment','wine_lot','NM-2026-01',
       JSON_OBJECT('incorrect_wine_lot','GRC-2026-01-P','incorrect_wine','Grecanico primary'),
       JSON_OBJECT('correct_wine_lot','NM-2026-01','correct_wine','Nerello',
                   'applied_at','2026-09-27 19:05:00','operation','pump-over',
                   'additions',JSON_ARRAY(
                       JSON_OBJECT('product','EnartisPro TINTO','quantity_g',46),
                       JSON_OBJECT('product','EnartisZym COLOR PLUS','product_lot','250258701','quantity_g',46)))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-189' AND a.action='correct_pump_over_lot_assignment'
);
