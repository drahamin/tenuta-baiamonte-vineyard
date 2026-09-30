-- Owner-confirmed Nerello nutrient addition on 29 September 2026.
-- The supplied photograph confirms NUTRIFERM ADVANCE identity and a nominal
-- 1 kg package. It does not show a dose range, product lot or post-use balance.

INSERT INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest)
VALUES
  (UUID(),'ENARTIS','NUTRIFERM ADVANCE','nutriferm advance','nutrients','Nutrients','nutrient','any','fermentation',
   'Yeast nutrient recorded from the owner-supplied 1 kg Enartis package. Use and identity are confirmed; projection remains disabled until its current purpose-specific technical sheet and rate are linked.',
   'https://www.enartis.com/',NULL,NULL,NULL,NULL,
   'Owner-supplied package front confirms identity and nominal pack size only; it does not support a dose projection.',0,
   'Owner-supplied NUTRIFERM ADVANCE package photograph received 2026-09-30',NOW(6),1)
ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),
  product_class=VALUES(product_class),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),
  description=VALUES(description),dose_basis=VALUES(dose_basis),dose_verified=0,source_url=VALUES(source_url),
  source_checked_at=VALUES(source_checked_at),present_in_latest=1,active=1;

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '19300000-0000-4000-8000-000000000001',s.estate_id,w.id,'NUTRIFERM ADVANCE','nutrient','applied',
       '2026-09-29 00:00:00',400.0000,'g',NULL,
       'Owner-confirmed 400 g Enartis NUTRIFERM ADVANCE addition to the Nerello on 29 September 2026. Exact application time, product lot and current APA/YAN contribution remain pending; total nutrient accounting must include this applied amount before another nutrition recommendation.',
       'David Rahamin','2026-09-29 00:00:00','Owner update 2026-09-30'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),
  applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),product_lot=VALUES(product_lot),
  reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '19300000-0000-4000-8000-000000000002',s.estate_id,s.id,w.id,'2026-09-29 00:00:00',
       'Fermentation nutrient addition',400.000,'g',
       'Nerello: 400 g Enartis NUTRIFERM ADVANCE added. Exact time and product lot were not supplied; include this amount in total nutrient accounting before any subsequent dose.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO enology_product_stock
  (id,estate_id,product_catalog_id,stock_key,supplier_name,product_lot,expires_on,package_size,package_unit,minimum_package_count,quantity_status,evidence_reference,notes)
SELECT UUID(),e.id,p.id,'owner-photo-2026-09-30-nutriferm-advance','Owner supplied',NULL,NULL,1.0000,'kg',1,'unverified',
       'Owner-supplied NUTRIFERM ADVANCE package photograph received 2026-09-30',
       'Nominal package size is 1 kg and 400 g use was confirmed on 2026-09-29. The pre-use package state and current remaining balance are not inferred.'
FROM estates e JOIN enology_product_catalog p ON p.manufacturer='ENARTIS' AND p.normalized_name='nutriferm advance'
ON DUPLICATE KEY UPDATE package_size=VALUES(package_size),package_unit=VALUES(package_unit),quantity_status=VALUES(quantity_status),
  evidence_reference=VALUES(evidence_reference),notes=VALUES(notes),active=1;

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'29 September 2026: 400 g Enartis NUTRIFERM ADVANCE added during Nerello fermentation; exact time and product lot pending.')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01'
  AND COALESCE(w.notes,'') NOT LIKE '%400 g Enartis NUTRIFERM ADVANCE%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-193','record_nerello_nutriferm_advance','enology_addition_event','19300000-0000-4000-8000-000000000001',
       JSON_OBJECT('wine_lot','NM-2026-01','product','NUTRIFERM ADVANCE','manufacturer','ENARTIS',
                   'applied_on','2026-09-29','quantity_g',400,'nominal_package_kg',1,
                   'pending',JSON_ARRAY('exact application time','product lot','current package balance','current technical sheet rate'))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-193' AND a.action='record_nerello_nutriferm_advance'
);
