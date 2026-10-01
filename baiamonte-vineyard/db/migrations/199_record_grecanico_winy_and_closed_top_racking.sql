-- Owner update supplied 1 October 2026: 30 g Enartis WINY potassium
-- metabisulfite was added to the primary Grecanico white, then the wine was
-- racked out of fermentation tank T-03 into a closed-top container. The
-- receiving vessel identity, rated capacity, material and exact operation time
-- were not supplied. A provisional logical vessel keeps the lot traceable
-- without inventing a physical tank number or a manufacturer-rated capacity.

INSERT INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest)
VALUES
  ('19900000-0000-4000-8000-000000000001','ENARTIS','WINY','winy','sulfiting_agents','Sulfiting agents','preservation','any','must,wine,post-fermentation,aging',
   'E224 potassium metabisulfite for antioxidant and antimicrobial protection of must and wine. One gram releases approximately 0.56 g SO2; this conversion does not establish the resulting free or total SO2 in the treated wine.',
   'https://shop-usa.enartis.com/winy-2','https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-Winy.pdf',
   NULL,NULL,NULL,'No generic cellar dose: select from current pH, free SO2, total SO2, wine condition and the enologist target. Official sheet states that 1 g WINY releases approximately 0.56 g SO2.',0,
   'https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-Winy.pdf','2026-10-01 00:00:00',1)
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),
  product_class=VALUES(product_class),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),
  description=VALUES(description),product_url=VALUES(product_url),pds_url=VALUES(pds_url),
  dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),dose_verified=0,
  source_url=VALUES(source_url),source_checked_at=VALUES(source_checked_at),present_in_latest=1,active=1;

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '19900000-0000-4000-8000-000000000002',s.estate_id,w.id,'WINY','other','applied',
       '2026-10-01 00:00:00',30.0000,'g',NULL,
       'Owner-confirmed 30 g Enartis WINY potassium metabisulfite addition to the primary Grecanico white on 1 October 2026, followed by racking from fermentation tank T-03 into a closed-top container. Exact application/racking time, product lot, receiving-vessel identity and rated capacity were not supplied. At the recorded 1,069.8 L lot volume the observed product rate is approximately 2.80 g/hL. The manufacturer conversion gives a theoretical 16.8 g SO2 equivalent in the product, but actual free and total SO2 are not inferred and require testing.',
       'David Rahamin','2026-10-01 00:00:00','Owner update 2026-10-01'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_product_stock
  (id,estate_id,product_catalog_id,stock_key,supplier_name,product_lot,expires_on,package_size,package_unit,minimum_package_count,quantity_status,evidence_reference,notes)
SELECT '19900000-0000-4000-8000-000000000003',e.id,p.id,'owner-photo-2026-10-01-winy','Owner supplied',NULL,NULL,1.0000,'kg',1,'unverified',
       'Owner-supplied WINY 1 kg package photograph received 2026-10-01',
       'Package identity and nominal 1 kg format are visible; owner confirmed 30 g used in GRC-2026-01-P on 1 October 2026. Pre-use fill and remaining balance are not inferred.'
FROM estates e JOIN enology_product_catalog p ON p.manufacturer='ENARTIS' AND p.normalized_name='winy'
ON DUPLICATE KEY UPDATE package_size=VALUES(package_size),package_unit=VALUES(package_unit),quantity_status=VALUES(quantity_status),
  evidence_reference=VALUES(evidence_reference),notes=VALUES(notes),active=1;

INSERT INTO cellar_containers
  (id,estate_id,code,name,container_type,material,capacity_l,location,status,notes,active)
SELECT '19900000-0000-4000-8000-000000000004',s.estate_id,'CT-GRC-P-2026',
       'Grecanico primary · closed-top container','tank',NULL,COALESCE(w.volume_l,1069.80),
       'Raiti cellar','in_use',
       'Provisional logical vessel created from the owner-confirmed 1 October 2026 racking. The stored capacity equals the known lot volume only because the schema requires a capacity; it is not a claim about the vessel rated capacity. Physical identifier, material, exact fill and rated capacity remain pending.',1
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE name=VALUES(name),container_type=VALUES(container_type),material=VALUES(material),
  capacity_l=VALUES(capacity_l),location=VALUES(location),status='in_use',notes=VALUES(notes),active=1;

INSERT INTO cellar_operations
  (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,notes)
SELECT '19900000-0000-4000-8000-000000000005',s.estate_id,s.id,w.id,d.id,
       '2026-10-01 00:00:00','WINY addition and closed-top racking',30.000,'g',
       'Owner-confirmed sequence: add 30 g Enartis WINY potassium metabisulfite to the primary Grecanico white, then rack from fermentation tank T-03 into a closed-top container. Date is confirmed; exact time, product lot and physical destination-vessel details were not supplied. Recorded lot volume remains 1,069.8 L until a post-racking measurement is supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
JOIN cellar_containers d ON d.estate_id=s.estate_id AND d.code='CT-GRC-P-2026'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE container_id=VALUES(container_id),operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE cellar_control_profiles cp
JOIN wine_lots w ON w.current_container_id=cp.container_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET cp.manual_volume_l=0,cp.manual_contents=NULL,cp.manual_stage='empty',
    cp.manual_reading_at='2026-10-01 00:00:00',cp.manual_updated_at='2026-10-01 00:00:00',
    cp.updated_by='Owner racking update 2026-10-01';

UPDATE cellar_containers c
JOIN wine_lots w ON w.current_container_id=c.id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET c.status='empty',c.notes=CONCAT_WS('\n',NULLIF(c.notes,''),'GRC-2026-01-P racked out to a closed-top container on 1 October 2026.')
WHERE c.code<>'CT-GRC-P-2026';

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers d ON d.estate_id=w.estate_id AND d.code='CT-GRC-P-2026'
SET w.current_container_id=d.id,w.stage='aging',w.lot_status='active',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'1 October 2026: 30 g Enartis WINY added, then the primary Grecanico white was racked from fermentation tank T-03 into a closed-top container. Receiving-vessel identity/rated capacity, exact operation time, product lot and post-racking volume were not supplied; recorded lot volume remains 1,069.8 L pending measurement.')
WHERE w.code='GRC-2026-01-P'
  AND COALESCE(w.notes,'') NOT LIKE '%30 g Enartis WINY added%';

INSERT INTO cellar_control_profiles
  (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_reading_at,manual_updated_at,updated_by)
SELECT '19900000-0000-4000-8000-000000000006',d.estate_id,d.id,'manual','not_configured',
       'Grecanico 2026 primary white · post-fermentation',w.volume_l,'aging',
       '2026-10-01 00:00:00','2026-10-01 00:00:00','Owner racking update 2026-10-01'
FROM cellar_containers d JOIN wine_lots w ON w.current_container_id=d.id
WHERE d.code='CT-GRC-P-2026' AND w.code='GRC-2026-01-P'
ON DUPLICATE KEY UPDATE manual_contents=VALUES(manual_contents),manual_volume_l=VALUES(manual_volume_l),
  manual_stage=VALUES(manual_stage),manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by);

UPDATE enology_process_profiles p
JOIN wine_lots w ON w.id=p.wine_lot_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET p.process_status='active',
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),'1 October 2026: alcoholic fermentation complete; 30 g WINY added and wine racked to a closed-top container. Continue post-fermentation protection and stability monitoring.')
WHERE w.code='GRC-2026-01-P'
  AND COALESCE(p.notes,'') NOT LIKE '%30 g WINY added and wine racked%';

INSERT INTO enology_test_requests
  (id,estate_id,season_id,wine_lot_id,requested_at,due_at,process_stage,sample_type,sample_scope,analytes_json,calculation_rules_json,status,requested_by,notes)
SELECT '19900000-0000-4000-8000-000000000007',s.estate_id,s.id,w.id,
       '2026-10-01 00:00:00','2026-10-02 12:00:00','post-fermentation','wine',
       'Primary Grecanico white after 30 g WINY addition, closed-top racking and complete homogenization',
       JSON_ARRAY('ph','free_so2','total_so2'),
       JSON_OBJECT('winy_rate_g_hl',ROUND(30/(w.volume_l/100),2),'winy_so2_equivalent_g',16.8,
                   'interpretation','Use measured pH and free/total SO2; do not treat the theoretical product conversion as a laboratory result.'),
       'scheduled','Owner update 2026-10-01',
       'Necessary post-racking protection check. Confirm actual free and total SO2 after the addition has homogenized; no further WINY dose is generated until these results are linked.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE requested_at=VALUES(requested_at),due_at=VALUES(due_at),process_stage=VALUES(process_stage),
  sample_type=VALUES(sample_type),sample_scope=VALUES(sample_scope),analytes_json=VALUES(analytes_json),
  calculation_rules_json=VALUES(calculation_rules_json),status=VALUES(status),requested_by=VALUES(requested_by),notes=VALUES(notes);

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '19900000-0000-4000-8000-000000000008',s.estate_id,'2026-10-01 00:00:00',
       'Grecanico WINY addition and closed-top racking',
       'Owner update: 30 g Enartis WINY potassium metabisulfite was added to the primary Grecanico white today, then the wine was racked from fermentation tank T-03 into a closed-top container. Exact time, product lot, physical destination-vessel identity/rating and post-racking volume were not supplied. Test pH plus free and total SO2 after homogenization before any additional sulfite decision.',
       JSON_ARRAY('owner-confirmed','grecanico','winy','potassium-metabisulfite','racking','closed-top','2026'),
       'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-199','record_grecanico_winy_closed_top_racking','wine_lot','GRC-2026-01-P',
       JSON_OBJECT('product','Enartis WINY','composition','E224 potassium metabisulfite','quantity_g',30,
                   'applied_on','2026-10-01','source_container','T-03','destination_container','CT-GRC-P-2026',
                   'destination_identity','pending','stage','aging','recorded_volume_l',1069.8,
                   'tests_next',JSON_ARRAY('pH','free SO2','total SO2'),
                   'not_inferred',JSON_ARRAY('exact operation time','product lot','destination rated capacity','post-racking volume','actual free SO2','actual total SO2'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-199' AND a.action='record_grecanico_winy_closed_top_racking');
