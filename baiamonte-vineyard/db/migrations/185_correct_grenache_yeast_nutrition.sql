-- Owner correction: Grenache fermentation was started with EnartisFerm D20
-- prepared with two spoonfuls of table sugar. NUTRIFERM AROM PLUS was not used
-- in this lot. Do not alter AROM PLUS records belonging to other wine lots.

DELETE a
FROM enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE a.id='18400000-0000-4000-8000-000000000002'
  AND a.additive_name='NUTRIFERM AROM PLUS';

DELETE o
FROM cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE o.id='18400000-0000-4000-8000-000000000005'
  AND o.operation_type='Nutrient addition';

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.reason_text='Owner-confirmed EnartisFerm D20 was the yeast in Wendy''s Grenache inoculation record. The recorded yeast quantity is 180, but its unit was not supplied and is not inferred. Preparation used 5 L water and two spoonfuls of table sugar for yeast support; cool/temper the yeast mixture to the 25 C must temperature, add into a hole on each side and cover the must. NUTRIFERM AROM PLUS was not used in this Grenache inoculation. Exact application time and product lot remain pending.',
    a.recorded_by='Owner correction 2026-09-27',a.approved_at='2026-09-27 00:00:00'
WHERE a.id='15500000-0000-4000-8000-000000000042'
  AND a.additive_name='EnartisFerm D20';

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET o.notes='EnartisFerm D20. Source records yeast quantity 180 without a unit. Prepared in 5 L water with two spoonfuls of table sugar and tempered to 25 C; exact time and product lot pending.'
WHERE o.id='18400000-0000-4000-8000-000000000003';

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '18500000-0000-4000-8000-000000000001',s.estate_id,s.id,w.id,'2026-09-10 00:00:00','Yeast preparation support',2.0000,'spoonfuls',
       'Table sugar used only in the EnartisFerm D20 preparation for the Grenache inoculation; not NUTRIFERM AROM PLUS. Exact spoon mass and application time were not recorded.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.notes=TRIM(REPLACE(st.notes,'Owner confirmed this product was used in the 2026 Grenache; remaining stock is not inferred.',''))
WHERE p.normalized_name='nutriferm arom plus';

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=REPLACE(
      w.notes,
      '10 September 2026: EnartisFerm D20 (recorded quantity 180; unit pending), EnartisTan ROUGE (quantity pending) and NUTRIFERM AROM PLUS (quantity pending) confirmed used. Exact product lots and application times remain pending.',
      '10 September 2026: EnartisFerm D20 (recorded yeast quantity 180; unit pending) and EnartisTan ROUGE (quantity pending) confirmed used. D20 preparation used 5 L water and two spoonfuls of table sugar for yeast support; NUTRIFERM AROM PLUS was not used in the Grenache inoculation. Exact product lots and application times remain pending.'
    )
WHERE w.estate_id=s.estate_id AND w.code='GRN-2026-01';

UPDATE notes n
JOIN wine_lots w ON w.id=n.related_id AND w.code='GRN-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET n.title='Products used in 2026 Grenache — corrected',
    n.body='Owner-confirmed product set: EnartisFerm D20 and EnartisTan ROUGE. Wendy''s source record supplies yeast quantity 180 but no unit, so the unit remains pending. The D20 preparation used 5 L water and two spoonfuls of table sugar for yeast support. NUTRIFERM AROM PLUS was not used in this Grenache inoculation. Tannin quantity, product lots and exact application times remain pending. Photographs establish product identity, not quantity or remaining stock.'
WHERE n.id='18400000-0000-4000-8000-000000000006';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-185','correct_grenache_yeast_nutrition','wine_lot','GRN-2026-01',
       JSON_OBJECT('yeast','EnartisFerm D20','recorded_yeast_quantity',180,'recorded_yeast_unit',NULL,
                   'yeast_preparation',JSON_OBJECT('water_l',5,'table_sugar_spoonfuls',2),
                   'tannin','EnartisTan ROUGE','not_used','NUTRIFERM AROM PLUS',
                   'pending',JSON_ARRAY('D20 quantity unit','tannin quantity','product lots','exact application times'))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-185' AND a.action='correct_grenache_yeast_nutrition'
);
