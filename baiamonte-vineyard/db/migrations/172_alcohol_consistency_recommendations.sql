ALTER TABLE enology_process_profiles
  ADD COLUMN IF NOT EXISTS target_potential_alcohol_pct DECIMAL(6,3) NULL AFTER potential_alcohol_pct;

INSERT INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest,active)
VALUES
  (UUID(),'NATURALIA INGREDIENTS','crystalMUSTGRAPE','crystalmustgrape','enrichment','Grape must enrichment','treatment','any','must,pre-fermentation,fermentation','Solid rectified concentrated grape must (crystalline grape dextrose and fructose) for technically calculated alcohol consistency.','https://naturaliaingredients.com/','https://naturaliaingredients.com/wp-content/uploads/2024/05/TS_CMG_24R7.pdf',1.68,1.68,'kg/hL/%vol','Official product sheet: 1.68 kg SRCM per 100 L increases potential alcohol by 1% vol (OIV OENO 466-2012).',1,'https://naturaliaingredients.com/wp-content/uploads/2024/05/TS_CMG_24R7.pdf',NOW(6),1,1)
ON DUPLICATE KEY UPDATE
  product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),product_class=VALUES(product_class),
  wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),description=VALUES(description),product_url=VALUES(product_url),
  pds_url=VALUES(pds_url),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),
  dose_verified=1,source_url=VALUES(source_url),source_checked_at=VALUES(source_checked_at),present_in_latest=1,active=1;

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,required_lab_analytes,lab_max_age_days,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on,active)
SELECT UUID(),p.id,'alcohol_consistency','Alcohol consistency to estate target','Calculate the remaining solid rectified concentrated grape must needed to bring split lots to the same target potential alcohol','any','must,pre-fermentation,fermentation','alcohol_consistency',1.68,1.68,'kg/hL/%vol','Official Naturalia conversion: 1.68 kg per 100 L for each +1% vol potential alcohol.','Weigh the calculated quantity. Dissolve it completely in a withdrawn portion of must, return it gradually with active mixing, homogenize the tank and record the product lot.','Retest potential alcohol after homogenization; the next recommendation uses the new exact-lot result.','Verified lot volume, current potential alcohol and estate target potential alcohol',NULL,NULL,'Compliance is a warning, not a calculation gate. Confirm current vintage, denomination, timing and enrichment limits before application.',NULL,'https://naturaliaingredients.com/wp-content/uploads/2024/05/TS_CMG_24R7.pdf','Naturalia product sheet TS-CMG 07, 2024-05-06; conversion checked 2026-09-18','2026-09-18',1
FROM enology_product_catalog p
WHERE p.manufacturer='NATURALIA INGREDIENTS' AND p.normalized_name='crystalmustgrape'
ON DUPLICATE KEY UPDATE
  protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),
  trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),
  preparation=VALUES(preparation),application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),
  required_lab_analytes=VALUES(required_lab_analytes),lab_max_age_days=VALUES(lab_max_age_days),incompatibilities=VALUES(incompatibilities),
  source_url=VALUES(source_url),source_revision=VALUES(source_revision),verified_on=VALUES(verified_on),active=1;

-- The 2026 Grecanico was split between the primary and final-press vessels.
-- Use one estate target so both recommendations converge; operators may edit it.
UPDATE enology_process_profiles p
JOIN wine_lots w ON w.id=p.wine_lot_id AND w.estate_id=p.estate_id
JOIN seasons s ON s.id=w.season_id
SET p.target_potential_alcohol_pct=12.0
WHERE s.vintage_year=2026
  AND LOWER(COALESCE(w.variety_summary,w.name,'')) LIKE '%grecanico%'
  AND p.target_potential_alcohol_pct IS NULL;
