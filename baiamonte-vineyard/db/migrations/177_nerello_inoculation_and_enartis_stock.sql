-- Owner-supplied 26 September 2026 cellar evidence and Nerello inoculation.
-- Package photographs establish identity/pack size only. Covered product variants,
-- post-use balances, nutrient quantity and exact application time remain explicit unknowns.

INSERT INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest)
VALUES
  (UUID(),'ENARTIS','NUTRIFERM AROM PLUS','nutriferm arom plus','nutrients','Nutrients','nutrient','any','must,pre-fermentation,fermentation','Autolyzed yeast and thiamine (0.15%) nutrient for aroma support and regular alcoholic fermentation.','https://www.enartis.com/',NULL,15,30,'g/hL','Owner-supplied package label: 15-30 g/hL; EU maximum shown on the package is 40 g/hL.',1,'Owner-supplied NUTRIFERM AROM PLUS package label photographed 2026-09-26',NOW(6),1),
  (UUID(),'ENARTIS','EnartisFerm — exact strain pending','enartisferm exact strain pending','yeast','Yeast','yeast','red','must,pre-fermentation','EnartisFerm yeast packet photographed for the 2026 Nerello inoculation; the strain name is covered and must not be inferred.','https://www.enartis.com/',NULL,NULL,NULL,NULL,'No projection until the exact strain and its current data sheet are identified.',0,'Owner-supplied EnartisFerm packet photograph 2026-09-26',NOW(6),1),
  (UUID(),'ENARTIS','EnartisZym — exact variant pending','enartiszym exact variant pending','enzymes','Enzymes','enzyme','red','must,fermentation','EnartisZym container photographed with the exact variant covered; retained as inventory evidence only.','https://www.enartis.com/',NULL,NULL,NULL,NULL,'No projection until the exact enzyme variant and current data sheet are identified.',0,'Owner-supplied EnartisZym container photograph 2026-09-26',NOW(6),1),
  (UUID(),'ENARTIS','COLOR PLUS','color plus','tannins','Tannins','tannin','red','must,fermentation','Product identity and 250 g supplied pack recorded from the Enodoro delivery document; exact formulation and dosing sheet remain to be linked.','https://www.enartis.com/',NULL,NULL,NULL,NULL,'Inventory only until the exact technical data sheet is linked.',0,'Enodoro DDT 241 dated 2026-09-25',NOW(6),1)
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),
  product_class=VALUES(product_class),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),
  description=VALUES(description),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),
  dose_basis=VALUES(dose_basis),dose_verified=VALUES(dose_verified),source_url=VALUES(source_url),
  source_checked_at=VALUES(source_checked_at),present_in_latest=1,active=1;

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,required_lab_analytes,lab_max_age_days,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on)
SELECT UUID(),p.id,'inoculation','Inoculation nutrient','Support aroma and regular alcoholic fermentation at yeast inoculation','any','must,pre-fermentation,fermentation','inoculation',15,30,'g/hL',
       'Owner-supplied package label; select within 15-30 g/hL from the complete YAN/APA nutrition plan.',
       'Dissolve in a small amount of water or must.','Add to the must at yeast inoculation and homogenize.',
       'Verified liquid volume, current YAN/APA, potential alcohol, selected yeast and total nutrient accounting',
       'yan,potential_alcohol',7,'Do not stack with other nutrient additions without total accounting. Package label states an EU maximum of 40 g/hL.',NULL,
       'Owner-supplied NUTRIFERM AROM PLUS package label photographed 2026-09-26','package label 2026-09-26','2026-09-26'
FROM enology_product_catalog p
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='nutriferm arom plus'
ON DUPLICATE KEY UPDATE protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),
  process_stages=VALUES(process_stages),trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),
  dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),preparation=VALUES(preparation),
  application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),
  required_lab_analytes=VALUES(required_lab_analytes),lab_max_age_days=VALUES(lab_max_age_days),
  incompatibilities=VALUES(incompatibilities),source_url=VALUES(source_url),source_revision=VALUES(source_revision),
  verified_on=VALUES(verified_on),active=1;

-- Current inventory: Pro TINTO remains a confirmed unopened-looking 1 kg pack.
-- AROM PLUS was a 1 kg pack but was opened/used today, so its remaining quantity
-- is deliberately NULL until weighed or counted. Covered variants are likewise
-- retained without invented pack sizes or balances.
INSERT INTO enology_product_stock
  (id,estate_id,product_catalog_id,stock_key,supplier_name,product_lot,expires_on,package_size,package_unit,minimum_package_count,quantity_status,evidence_reference,notes)
SELECT UUID(),e.id,p.id,x.stock_key,'Enodoro',NULL,NULL,x.package_size,x.package_unit,1,x.quantity_status,
       'Owner photographs plus Enodoro DDT 241 dated 2026-09-25',x.notes
FROM estates e
CROSS JOIN (
  SELECT 'enartispro tinto' product_key,'ddt-241-2026-09-25-pro-tinto' stock_key,1.0000 package_size,'kg' package_unit,'counted' quantity_status,'One 1 kg pack photographed and listed on the delivery document.' notes
  UNION ALL SELECT 'nutriferm arom plus','ddt-241-2026-09-25-nutriferm-arom-plus',NULL,NULL,'unverified','Purchased 1 kg pack photographed; nutrient was used on 2026-09-26, but the applied amount and current remainder were not supplied.'
  UNION ALL SELECT 'enartisferm exact strain pending','ddt-241-2026-09-25-enartisferm-pending',NULL,NULL,'unverified','EnartisFerm packets photographed; 500 g was applied to Nerello on 2026-09-26. Exact strain, acquired count and remaining balance are unresolved.'
  UNION ALL SELECT 'enartiszym exact variant pending','ddt-241-2026-09-25-enartiszym-pending',NULL,NULL,'unverified','One EnartisZym container photographed; exact variant, pack size and current balance are obscured.'
  UNION ALL SELECT 'color plus','ddt-241-2026-09-25-color-plus',0.2500,'kg','unverified','Delivery document lists a 0.250 kg pack; current unopened/on-hand status has not been confirmed.'
) x
JOIN enology_product_catalog p ON p.manufacturer='ENARTIS' AND p.normalized_name=x.product_key
ON DUPLICATE KEY UPDATE supplier_name=VALUES(supplier_name),package_size=VALUES(package_size),package_unit=VALUES(package_unit),
  minimum_package_count=VALUES(minimum_package_count),quantity_status=VALUES(quantity_status),
  evidence_reference=VALUES(evidence_reference),notes=VALUES(notes),active=1;

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.stage='fermentation',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'26 September 2026: inoculated with 500 g EnartisFerm yeast (exact strain pending) and added NUTRIFERM AROM PLUS nutrient (quantity pending).')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01';

INSERT INTO enology_process_profiles
  (id,estate_id,wine_lot_id,wine_color,process_status,inoculated_at,notes)
SELECT UUID(),s.estate_id,w.id,'red','active','2026-09-26 00:00:00',
       'Nerello inoculated 26 September 2026. Exact yeast strain, nutrient quantity, product lots, exact time, vessel and must volume remain to be recorded.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE wine_color='red',process_status='active',inoculated_at=VALUES(inoculated_at),
  notes=CONCAT_WS('\n',NULLIF(enology_process_profiles.notes,''),VALUES(notes));

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '17700000-0000-4000-8000-000000000001',s.estate_id,w.id,'EnartisFerm — exact strain pending','yeast','applied',
       '2026-09-26 00:00:00',500.0000,'g',NULL,
       'Owner-confirmed Nerello inoculation. Exact EnartisFerm strain, product lot and application time were not supplied; do not infer the strain from the covered packet.',
       'David Rahamin','2026-09-26 00:00:00','Owner update 2026-09-26'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '17700000-0000-4000-8000-000000000002',s.estate_id,w.id,'NUTRIFERM AROM PLUS','nutrient','applied',
       '2026-09-26 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed nutrient addition at Nerello inoculation. Applied quantity, product lot and exact time were not supplied and remain explicit pending fields.',
       'David Rahamin','2026-09-26 00:00:00','Owner update 2026-09-26'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '17700000-0000-4000-8000-000000000003',s.estate_id,s.id,w.id,'2026-09-26 00:00:00','Yeast inoculation',500.0000,'g',
       'EnartisFerm yeast; exact strain, product lot and application time pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '17700000-0000-4000-8000-000000000004',s.estate_id,s.id,w.id,'2026-09-26 00:00:00','Nutrient addition',NULL,NULL,
       'NUTRIFERM AROM PLUS added with the Nerello inoculation; amount, product lot and exact time pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '17700000-0000-4000-8000-000000000005',s.estate_id,'2026-09-26 00:00:00','Nerello inoculation and Enartis delivery',
       'Nerello: 500 g EnartisFerm yeast and NUTRIFERM AROM PLUS nutrient added today. Exact yeast strain, nutrient amount, product lots and exact time remain pending. Inventory evidence also records EnartisPro TINTO 1 kg, COLOR PLUS 250 g, and covered EnartisZym/EnartisFerm products without guessing their variants.',
       JSON_ARRAY('owner-confirmed','nerello-mascalese','enology','inoculation','inventory','2026'),'wine_lot',w.id
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-177','record_nerello_inoculation_and_stock','wine_lot','NM-2026-01',
       JSON_OBJECT('applied_on','2026-09-26','yeast','EnartisFerm - exact strain pending','yeast_quantity_g',500,
                   'nutrient','NUTRIFERM AROM PLUS','nutrient_quantity',NULL,
                   'inventory',JSON_ARRAY('EnartisPro TINTO 1 kg','COLOR PLUS 250 g','EnartisZym variant pending'),
                   'pending',JSON_ARRAY('exact yeast strain','nutrient quantity','product lots','exact application time','vessel','must volume'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-177' AND a.entity_id='NM-2026-01');
