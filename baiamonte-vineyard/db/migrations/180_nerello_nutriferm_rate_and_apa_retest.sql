-- Owner correction: NUTRIFERM AROM PLUS was applied to the approximately
-- 1,600 L Nerello must at 30 g/hL. Total = 30 * 16 hL = 480 g.

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.quantity=480.0000,a.unit='g',
    a.reason_text='Owner-confirmed NUTRIFERM AROM PLUS addition at 30 g/hL to approximately 1,600 L (16 hL) Nerello must: 480 g total. Run APA/YAN now and recalculate any further nutrition adjustment from the result.'
WHERE a.id='17700000-0000-4000-8000-000000000002';

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET o.amount=480.000,o.unit='g',
    o.notes='NUTRIFERM AROM PLUS applied at 30 g/hL to approximately 1,600 L Nerello must: 480 g total. APA/YAN retest follows; exact application time and product lot remain pending.'
WHERE o.id='17700000-0000-4000-8000-000000000004';

UPDATE enology_product_stock st
JOIN enology_product_catalog p ON p.id=st.product_catalog_id
SET st.package_size=0.5200,st.package_unit='kg',st.minimum_package_count=1,st.quantity_status='counted',
    st.notes='Original photographed pack was 1 kg. Owner confirmed 480 g applied to Nerello on 2026-09-26, leaving approximately 520 g.'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='nutriferm arom plus'
  AND st.stock_key='ddt-241-2026-09-25-nutriferm-arom-plus';

INSERT IGNORE INTO enology_test_requests
  (id,estate_id,season_id,wine_lot_id,requested_at,due_at,process_stage,sample_type,sample_scope,analytes_json,calculation_rules_json,status,requested_by,notes)
SELECT '18000000-0000-4000-8000-000000000001',s.estate_id,s.id,w.id,'2026-09-26 00:00:00','2026-09-26 00:00:00',
       'fermentation','must','Nerello must, approximately 1,600 L: APA/YAN after 480 g NUTRIFERM AROM PLUS addition',
       JSON_ARRAY('yan'),
       JSON_OBJECT('on_result','refresh_enology_additive_predictions','adjustment_basis','new APA/YAN result, potential alcohol, 1,600 L lot volume, yeast strain and total nutrient already applied','already_applied',JSON_OBJECT('product','NUTRIFERM AROM PLUS','quantity_g',480,'rate_g_hl',30)),
       'scheduled','David Rahamin','Run APA/YAN now. When the result arrives, update the Nerello nutrition recommendation from the measured result and total 480 g already applied; do not repeat the original dose automatically.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026;

UPDATE notes n
JOIN wine_lots w ON w.id=n.related_id AND n.related_type='wine_lot' AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET n.body='Nerello: 500 g EnartisFerm Q GRACE (lot L530283) and 480 g NUTRIFERM AROM PLUS added 26 September 2026. Nutrient rate was 30 g/hL against the approximately 1,600 L must volume. Run APA/YAN now; the next nutrition adjustment must use that result and account for the full 480 g already applied. Q GRACE receipt supplied 1.500 kg as three 500 g packs, leaving two packs / 1.000 kg. Approximately 520 g NUTRIFERM AROM PLUS remains from the photographed 1 kg bag. Exact nutrient product lot and application times remain pending.'
WHERE n.id='17700000-0000-4000-8000-000000000005';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-180','confirm_nutrient_rate_and_schedule_apa','enology_addition','17700000-0000-4000-8000-000000000002',
       JSON_OBJECT('product','NUTRIFERM AROM PLUS','lot_volume_l',1600,'rate_g_hl',30,'applied_quantity_g',480,
                   'remaining_stock_g',520,'next_test','APA/YAN','next_action','recalculate nutrition adjustment from result','pending',JSON_ARRAY('nutrient product lot','exact application time'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-180' AND a.entity_id='17700000-0000-4000-8000-000000000002');
