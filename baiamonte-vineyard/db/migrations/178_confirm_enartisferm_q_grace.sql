-- Owner correction: the yeast shown and used for the 2026 Nerello is
-- EnartisFerm Q GRACE, as written on Enodoro DDT 241 dated 2026-09-25.

INSERT INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest)
VALUES
  (UUID(),'ENARTIS','EnartisFerm Q GRACE','enartisferm q grace','yeast','Yeast','yeast','red,white','must,pre-fermentation','Saccharomyces cerevisiae selected for premium varietal wines, aromatic complexity, elegance and balanced structure. Easytech strain suitable for direct inoculation.','https://shop-usa.enartis.com/enartisferm-q-grace','https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermQGrace.pdf',20,40,'g/hL','Official Enartis product page and technical data sheet.',1,'https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermQGrace.pdf',NOW(6),1)
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),
  product_class=VALUES(product_class),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),
  description=VALUES(description),product_url=VALUES(product_url),pds_url=VALUES(pds_url),dose_min=VALUES(dose_min),
  dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),dose_verified=1,
  source_url=VALUES(source_url),source_checked_at=VALUES(source_checked_at),present_in_latest=1,active=1;

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,required_lab_analytes,lab_max_age_days,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on)
SELECT UUID(),p.id,'standard_inoculation','Premium varietal-wine inoculation','Enhance varietal character, aromatic complexity, elegance and balanced structure','red,white','must,pre-fermentation','inoculation',20,40,'g/hL',
       'Official Enartis product page and technical data sheet.',
       'Easytech strain: direct inoculation is supported by the current technical sheet; follow the packet instructions and homogenize thoroughly.',
       'Add at yeast inoculation and distribute uniformly through the must.',
       'Verified liquid volume, must temperature, potential alcohol, one current YAN/APA result and a complete nutrition plan',
       'ph,total_acidity,potential_alcohol,yan',7,
       'Keep within the 16-30 C fermentation range stated by the current technical sheet and account for all nutrient additions.',NULL,
       'https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermQGrace.pdf','official sheet accessed 2026-09-26','2026-09-26'
FROM enology_product_catalog p
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartisferm q grace'
ON DUPLICATE KEY UPDATE protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),
  process_stages=VALUES(process_stages),trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),
  dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),preparation=VALUES(preparation),
  application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),
  required_lab_analytes=VALUES(required_lab_analytes),lab_max_age_days=VALUES(lab_max_age_days),
  incompatibilities=VALUES(incompatibilities),source_url=VALUES(source_url),source_revision=VALUES(source_revision),
  verified_on=VALUES(verified_on),active=1;

-- Receipt: 1.500 kg supplied as 500 g packs. One 500 g pack was used today,
-- leaving two 500 g packs (1.000 kg) as the calculated current balance.
INSERT INTO enology_product_stock
  (id,estate_id,product_catalog_id,stock_key,supplier_name,product_lot,expires_on,package_size,package_unit,minimum_package_count,quantity_status,evidence_reference,notes)
SELECT UUID(),e.id,p.id,'ddt-241-2026-09-25-q-grace','Enodoro','L530283',NULL,0.5000,'kg',2,'counted',
       'Enodoro DDT 241 dated 2026-09-25 plus owner-confirmed 500 g use on 2026-09-26',
       'Receipt supplied 1.500 kg as 500 g packs; one 500 g pack was applied to Nerello, leaving two 500 g packs (1.000 kg).'
FROM estates e JOIN enology_product_catalog p ON p.manufacturer='ENARTIS' AND p.normalized_name='enartisferm q grace'
ON DUPLICATE KEY UPDATE supplier_name=VALUES(supplier_name),product_lot=VALUES(product_lot),package_size=VALUES(package_size),
  package_unit=VALUES(package_unit),minimum_package_count=VALUES(minimum_package_count),quantity_status=VALUES(quantity_status),
  evidence_reference=VALUES(evidence_reference),notes=VALUES(notes),active=1;

UPDATE enology_product_stock s
JOIN enology_product_catalog p ON p.id=s.product_catalog_id
SET s.active=0,s.notes=CONCAT_WS(' ',NULLIF(s.notes,''),'Superseded by owner-confirmed EnartisFerm Q GRACE identity.')
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartisferm exact strain pending';

UPDATE enology_product_catalog
SET active=0,present_in_latest=0,description=CONCAT_WS(' ',NULLIF(description,''),'Resolved as EnartisFerm Q GRACE by owner correction and Enodoro DDT 241.')
WHERE manufacturer='ENARTIS' AND normalized_name='enartisferm exact strain pending';

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.additive_name='EnartisFerm Q GRACE',a.product_lot='L530283',
    a.reason_text='Owner-confirmed 500 g EnartisFerm Q GRACE inoculation for Nerello. Product identity and lot L530283 are recorded from Enodoro DDT 241 dated 2026-09-25; exact application time remains pending.'
WHERE a.id='17700000-0000-4000-8000-000000000001';

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET o.notes='EnartisFerm Q GRACE, lot L530283; 500 g applied. Exact application time pending.'
WHERE o.id='17700000-0000-4000-8000-000000000003';

UPDATE enology_process_profiles p
JOIN wine_lots w ON w.id=p.wine_lot_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET p.approved_yeast='EnartisFerm Q GRACE',
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),'Owner confirmed the inoculation yeast as EnartisFerm Q GRACE from Enodoro DDT 241; lot L530283.')
WHERE p.estate_id=s.estate_id;

UPDATE notes n
JOIN wine_lots w ON w.id=n.related_id AND n.related_type='wine_lot' AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET n.body='Nerello: 500 g EnartisFerm Q GRACE (lot L530283) and NUTRIFERM AROM PLUS nutrient added 26 September 2026. The Q GRACE receipt supplied 1.500 kg as three 500 g packs, leaving two packs / 1.000 kg after this use. Nutrient amount, nutrient product lot and exact application times remain pending. Inventory evidence also records EnartisPro TINTO 1 kg, COLOR PLUS 250 g, and an EnartisZym container whose exact variant remains covered.'
WHERE n.id='17700000-0000-4000-8000-000000000005';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-178','resolve_yeast_identity','enology_addition','17700000-0000-4000-8000-000000000001',
       JSON_OBJECT('product','EnartisFerm Q GRACE','product_lot','L530283','applied_quantity_g',500,
                   'received_quantity_kg',1.500,'remaining_quantity_kg',1.000,'remaining_packs',2,
                   'source','Enodoro DDT 241 dated 2026-09-25','pending',JSON_ARRAY('exact application time'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-178' AND a.entity_id='17700000-0000-4000-8000-000000000001');
