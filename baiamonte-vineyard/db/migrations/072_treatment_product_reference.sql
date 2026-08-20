CREATE TABLE IF NOT EXISTS treatment_product_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  concentrate_form ENUM('liquid','water_dispersible_granule','water_soluble_powder','wettable_powder','gel','unknown') NOT NULL DEFAULT 'unknown',
  formulation_code VARCHAR(80) NULL,
  final_application_medium ENUM('water_spray') NOT NULL DEFAULT 'water_spray',
  verification_status ENUM('verified','historical_only','needs_container_label','expired') NOT NULL DEFAULT 'needs_container_label',
  estate_authorization_status ENUM('confirmed','not_confirmed') NOT NULL DEFAULT 'not_confirmed',
  estate_authorization_confirmed_on DATE NULL,
  authorization_notes TEXT NULL,
  measure_unit VARCHAR(30) NULL,
  density_kg_l DECIMAL(10,5) NULL,
  density_source VARCHAR(255) NULL,
  mixing_position SMALLINT UNSIGNED NULL,
  mixing_instructions TEXT NULL,
  compatibility_notes TEXT NULL,
  water_quality_notes TEXT NULL,
  label_version_date DATE NULL,
  label_verified_on DATE NULL,
  label_url TEXT NULL,
  eligible_for_projection TINYINT(1) NOT NULL DEFAULT 0,
  source_summary TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_product_profile (estate_id,product_id),
  KEY ix_treatment_profile_ready (estate_id,verification_status,eligible_for_projection,active),
  CONSTRAINT fk_treatment_profile_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_profile_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS treatment_product_options (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  crop_scope ENUM('vineyard','olives') NOT NULL,
  target_code VARCHAR(100) NOT NULL DEFAULT 'any',
  mixture_role ENUM('primary','support','adjuvant','nutrition') NOT NULL,
  default_decision ENUM('candidate','not_selected','blocked') NOT NULL DEFAULT 'blocked',
  selection_conditions TEXT NULL,
  exclusion_reason TEXT NULL,
  water_rate_min DECIMAL(12,3) NULL,
  water_rate_max DECIMAL(12,3) NULL,
  water_rate_unit ENUM('g/L','ml/100 L') NULL,
  minimum_rate_per_ha DECIMAL(12,3) NULL,
  minimum_rate_per_ha_unit ENUM('kg/ha','L/ha') NULL,
  compatibility_status ENUM('verified_compatible','conditional','incompatible','not_verified') NOT NULL DEFAULT 'not_verified',
  compatibility_conditions TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_product_option (estate_id,product_id,crop_scope,target_code,mixture_role),
  KEY ix_treatment_option_target (estate_id,crop_scope,target_code,active),
  CONSTRAINT fk_treatment_option_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_option_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS treatment_product_evidence (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  evidence_type ENUM('invoice','historical_application','container_label','official_register','manufacturer_label','technical_product_page','sds','agronomist_review','owner_document') NOT NULL,
  source_key VARCHAR(190) NOT NULL,
  source_reference TEXT NULL,
  observed_form VARCHAR(100) NULL,
  observed_rate DECIMAL(12,3) NULL,
  observed_rate_unit VARCHAR(40) NULL,
  observed_water_l DECIMAL(12,2) NULL,
  evidence_date DATE NULL,
  verification_status ENUM('verified','historical_only','needs_review','rejected','expired') NOT NULL DEFAULT 'needs_review',
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_product_evidence (estate_id,product_id,evidence_type,source_key),
  KEY ix_treatment_evidence_product (product_id,evidence_date),
  CONSTRAINT fk_treatment_evidence_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_evidence_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS treatment_regulatory_sources (
  id CHAR(36) PRIMARY KEY,
  source_code VARCHAR(100) NOT NULL UNIQUE,
  authority VARCHAR(180) NOT NULL,
  source_scope VARCHAR(255) NOT NULL,
  version_date DATE NULL,
  source_url TEXT NOT NULL,
  refresh_frequency VARCHAR(80) NULL,
  checked_on DATE NOT NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS spray_equipment_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  equipment_id CHAR(36) NOT NULL,
  application_method ENUM('water_spray') NOT NULL DEFAULT 'water_spray',
  tank_capacity_l DECIMAL(12,2) NULL,
  usable_capacity_l DECIMAL(12,2) NULL,
  calibrated_on DATE NULL,
  calibration_status ENUM('verified','needs_measurement','expired') NOT NULL DEFAULT 'needs_measurement',
  nozzle_setup VARCHAR(255) NULL,
  flow_l_min DECIMAL(10,3) NULL,
  operating_pressure_bar DECIMAL(10,3) NULL,
  travel_speed_kph DECIMAL(10,3) NULL,
  carrier_rate_l_ha DECIMAL(12,2) NULL,
  source_reference TEXT NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_spray_equipment_profile (estate_id,equipment_id),
  CONSTRAINT fk_spray_profile_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_spray_profile_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS equipment_id CHAR(36) NULL AFTER equipment_name;
CREATE INDEX IF NOT EXISTS ix_spray_application_equipment ON spray_applications (equipment_id);
ALTER TABLE spray_applications ADD CONSTRAINT fk_spray_application_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE SET NULL;

UPDATE products SET product_type='fertilizer',unit='L',supplier='BioAtlantis / Kalos',notes='Physical estate container: K&A FRONTIERE 2.0, liquid organic nitrogen fertilizer with fluid yeast extract and brown algae; owner confirmed authorized and in date on 2026-08-20.' WHERE name='FRONTIERE';
UPDATE products SET product_type='fertilizer',unit='L',supplier='Ben Star / Kalos',notes='Physical estate container: natural plant inducer; owner confirmed authorized and in date on 2026-08-20.' WHERE name='REPENTE';
UPDATE products SET product_type='fertilizer',unit='L',supplier='Ben Star / Kalos',notes='Physical estate container: silica gel defense enhancer; owner confirmed authorized and in date on 2026-08-20.' WHERE name='GEL DI SILICE';
UPDATE products SET unit='L',supplier='Ben Star / Kalos',notes='Physical estate container identifies IMPULSIVE PREMIUM F; owner confirmed authorized and in date on 2026-08-20.' WHERE name='IMPULSIVE PREMIUM';
UPDATE products SET product_type='fertilizer',unit='kg',supplier='Kalos',notes='Kalos RESOLVE biostimulant, water-dispersible powder in a 5 kg pack. Technical directions record 5 g/L for vineyard foliar use and a minimum 2 kg/ha; owner confirmed authorized and in-date estate stock on 2026-08-20. No density or unit conversion is inferred: projected quantity is calculated directly in grams from the water volume.' WHERE name='RESOLVE';
UPDATE treatment_purchase_evidence pe JOIN products p ON p.id=pe.product_id
SET pe.package_unit='kg',pe.quantity_unit='kg',pe.notes=CONCAT_WS(' · ',pe.notes,'Package unit reconciled to the documented RESOLVE 5 kg water-dispersible powder pack; quantity remains the invoice total.')
WHERE p.name='RESOLVE';
UPDATE products SET name='OSSICLOR 20 BLU FLOW',unit='L',supplier='Manica',notes='Physical estate container and official register identify OSSICLOR 20 BLU FLOW, copper oxychloride 20%, registration 012723; owner confirmed authorized and in date on 2026-08-20.' WHERE name='OSSICLOR 20 MANICA';
UPDATE products SET notes='Physical estate container identifies SACRON 45 WG, cymoxanil 45%, registration 012916. Estate owner confirmed authorization and in-date stock on 2026-08-20; a conflicting Ministry snapshot date is retained as evidence requiring reconciliation, not treated as proof of expiry.' WHERE name='SACRON 45 WG';
UPDATE product_authorized_uses u JOIN products p ON p.id=u.product_id
SET u.authorization_status='authorized',u.authorization_expires_on=NULL,u.label_verified_on='2026-08-20',
    u.notes=CONCAT_WS(' · ',u.notes,'Estate owner confirmed authorization and in-date stock on 2026-08-20. Reconcile the conflicting registry snapshot before final approval.')
WHERE p.name='SACRON 45 WG';

INSERT INTO treatment_product_profiles (id,estate_id,product_id,concentrate_form,measure_unit,verification_status,source_summary)
SELECT UUID(),p.estate_id,p.id,'unknown',p.unit,'needs_container_label',
  'Catalog reference created from the authoritative products table. Formulation and current container label remain to be verified.'
FROM products p
WHERE p.active=1 AND p.product_type IN ('plant_protection','fertilizer','other')
ON DUPLICATE KEY UPDATE measure_unit=COALESCE(treatment_product_profiles.measure_unit,VALUES(measure_unit)),active=1;

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='water_dispersible_granule',r.formulation_code='WG',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_position=20,r.mixing_instructions='Add to water only in the order and manner stated on the current container label while maintaining the required agitation.',
    r.compatibility_notes='Tank-mix compatibility and sequence require agronomist confirmation for every proposed combination.',
    r.label_verified_on='2026-08-19',r.label_url='https://www.uplitalia.com/it/prodotto/3',r.eligible_for_projection=1,
    r.source_summary='Product identity, WG formulation and current authorized use are tied to the recorded official/manufacturer label evidence.'
WHERE p.name='MICROTHIOL DISPERSS';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='water_dispersible_granule',r.formulation_code='WG',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_position=20,r.mixing_instructions='Add to water only in the order and manner stated on the current container label while maintaining the required agitation.',
    r.compatibility_notes='Tank-mix compatibility, copper limits and sequence require agronomist confirmation for every proposed combination.',
    r.label_verified_on='2026-08-19',r.label_url='https://www.manica.com/prodotti/ossicloruro-di-rame-ossiclor-35-wg/',r.eligible_for_projection=1,
    r.source_summary='Product identity, WG formulation and current authorized use are tied to the recorded official/manufacturer label evidence.'
WHERE p.name='OSSICLOR 35 WG';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='water_dispersible_granule',r.formulation_code='WG',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',
    r.authorization_notes='Estate owner confirmed current authorization and in-date stock. Ministry open-data snapshot dated 2026-08-17 contains an administrative date of 2026-08-15; reconcile against the latest authorized label before final agronomist approval.',
    r.label_verified_on='2026-08-20',r.label_url='https://uplitalia.com/it/prodotto/36',r.eligible_for_projection=1,
    r.source_summary='Physical container verifies identity and WG formulation. Owner authorization is recorded separately from the conflicting registry snapshot.'
WHERE p.name='SACRON 45 WG';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.measure_unit='L',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=1,
    r.mixing_instructions='Shake before use and dilute in water according to the physical label.',r.source_summary='Physical container verifies liquid formulation and vineyard foliar directions of 2 to 3 L/ha.'
WHERE p.name='IMPULSIVE PREMIUM';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='water_soluble_powder',r.measure_unit='kg',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=1,
    r.mixing_instructions='Add gradually to treatment water under continuous agitation at 5 g/L. Maintain agitation through application and follow the current directions and agronomist instructions.',
    r.compatibility_notes='Exact tank-mix compatibility is not verified. Keep separate unless the current directions permit the combination and the Agronomist approves it after a compatibility test.',
    r.label_verified_on='2026-08-20',r.label_url='https://www.agricolaalbese.it/kalos-resolve-biostimolante-5-kg-bio.html',
    r.source_summary='Technical product page records a 5 kg water-dispersible powder, 5 g/L vineyard foliar rate and minimum 2 kg/ha. Owner confirms authorized and in-date estate stock.'
WHERE p.name='RESOLVE';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='gel',r.measure_unit='L',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=1,
    r.mixing_instructions='Shake very well before use; dilute 100 to 300 ml per 100 L water for foliar application.',r.compatibility_notes='Perform a small compatibility test. Do not mix with strong acids or strong bases.',
    r.source_summary='Physical container resolves the invoice/history mismatch: foliar direction is expressed as volume per 100 L water; no density conversion is inferred.'
WHERE p.name='GEL DI SILICE';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.measure_unit='L',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=1,
    r.mixing_instructions='Shake before use and dilute in water according to the physical label.',r.compatibility_notes='Perform a jar test, especially with strong acids or alkaline products.',
    r.source_summary='Physical container verifies liquid formulation and vineyard foliar directions of 1 to 3 L/ha.'
WHERE p.name='REPENTE';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.measure_unit='L',r.verification_status='needs_container_label',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=0,
    r.source_summary='Physical container verifies identity, composition and liquid formulation, but the photographed face does not show a vineyard foliar rate.'
WHERE p.name='FRONTIERE';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.formulation_code='SC',r.measure_unit='L',r.verification_status='verified',r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',r.eligible_for_projection=0,
    r.label_verified_on='2026-08-20',r.source_summary='Physical container and official register verify OSSICLOR 20 BLU FLOW, copper oxychloride 20%, registration 012723. Current crop, target, dose, PHI and sequence still require the latest full label.'
WHERE p.name='OSSICLOR 20 BLU FLOW';

INSERT INTO treatment_product_options (id,estate_id,product_id,crop_scope,target_code,mixture_role,default_decision,selection_conditions,exclusion_reason)
SELECT UUID(),p.estate_id,p.id,x.crop_scope,x.target_code,x.mixture_role,x.default_decision,x.selection_conditions,x.exclusion_reason
FROM products p JOIN (
  SELECT 'MICROTHIOL DISPERSS' product_name,'vineyard' crop_scope,'powdery_mildew' target_code,'primary' mixture_role,'candidate' default_decision,'Current target, label, rate, PHI, weather and agronomist approval must all pass.' selection_conditions,NULL exclusion_reason UNION ALL
  SELECT 'OSSICLOR 35 WG','vineyard','downy_mildew','primary','candidate','Current target, label, copper limits, rate, PHI, weather and agronomist approval must all pass.',NULL UNION ALL
  SELECT 'SACRON 45 WG','vineyard','downy_mildew','primary','candidate','Owner-confirmed authorization, current label, target, rate, PHI, weather, registry discrepancy review and agronomist approval must all pass.',NULL UNION ALL
  SELECT 'RESOLVE','vineyard','powdery_mildew','support','not_selected','Select only for a documented support need; use 5 g/L in water with a minimum 2 kg/ha, and require current directions plus Agronomist approval.','A disease-risk signal alone does not justify automatic addition, and exact tank-mix compatibility is not verified.' UNION ALL
  SELECT 'GEL DI SILICE','vineyard','powdery_mildew','support','not_selected','Select only for documented biotic or abiotic stress; use 100 to 300 ml/100 L water, perform a compatibility test, and obtain agronomist approval.','A disease-risk signal alone does not justify automatic addition.' UNION ALL
  SELECT 'IMPULSIVE PREMIUM','vineyard','any','nutrition','not_selected','Select only for a documented nutritional/biostimulant need; physical label permits 2 to 3 L/ha foliar on fruit trees, olive and vine.','A disease-risk signal alone does not justify nutritional support.' UNION ALL
  SELECT 'TERRAPLUS SOLUB NPK 8-7-6','vineyard','any','nutrition','not_selected','Select only for a documented nutrient need and a verified foliar-water application label.','Not a disease-control product and its spray formulation is not verified.' UNION ALL
  SELECT 'FRONTIERE','vineyard','any','support','blocked','Capture the rate panel and current directions before projecting a water-spray mixture.','The photographed label verifies identity and composition but not a vineyard foliar rate.' UNION ALL
  SELECT 'REPENTE','vineyard','any','support','not_selected','Select only for a recognized need; physical label permits 1 to 3 L/ha vineyard foliar use. Perform the required compatibility test and obtain agronomist approval.','Not automatically selected from a disease-risk signal.' UNION ALL
  SELECT 'OSSICLOR 20 BLU FLOW','vineyard','any','primary','blocked','Verify current crop, target, dose, PHI and application sequence from the latest full label.','Identity and current estate authorization are recorded, but the photographed panel is not the complete use label.' UNION ALL
  SELECT 'FERTICUS 18 M','vineyard','any','nutrition','blocked','Container identity, current directions, rate, compatibility and sequence must be verified.','Historical use is evidence, not a current mixing instruction.'
) x ON x.product_name=p.name
ON DUPLICATE KEY UPDATE default_decision=VALUES(default_decision),selection_conditions=VALUES(selection_conditions),exclusion_reason=VALUES(exclusion_reason),active=1;

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.compatibility_status='not_verified',
    o.compatibility_conditions='Do not combine automatically. Confirm the exact products, current directions, crop, rates, water quality, order, PHI and a physical compatibility test with the Agronomist.'
WHERE o.active=1;

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.water_rate_min=5,o.water_rate_max=5,o.water_rate_unit='g/L',o.minimum_rate_per_ha=2,o.minimum_rate_per_ha_unit='kg/ha',
    o.compatibility_status='not_verified',o.compatibility_conditions='Keep separate unless the current directions permit the exact combination and the Agronomist approves it after a compatibility test.'
WHERE p.name='RESOLVE' AND o.crop_scope='vineyard';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.water_rate_min=100,o.water_rate_max=300,o.water_rate_unit='ml/100 L',o.compatibility_status='conditional',
    o.compatibility_conditions='Do not combine with strong acids or strong bases. Use only when current directions permit the exact mixture and the Agronomist approves a compatibility test.'
WHERE p.name='GEL DI SILICE' AND o.crop_scope='vineyard';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.compatibility_status='conditional',o.compatibility_conditions='Use only when the current directions permit the exact combination and the Agronomist approves it after a compatibility test, especially with acidic or alkaline products.'
WHERE p.name='REPENTE' AND o.crop_scope='vineyard';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.compatibility_status='not_verified',o.compatibility_conditions='Sulfur and copper products must remain separate unless the exact combination is explicitly permitted by both current directions and approved by the Agronomist after a compatibility test.'
WHERE p.name IN ('MICROTHIOL DISPERSS','OSSICLOR 35 WG','OSSICLOR 20 BLU FLOW') AND o.crop_scope='vineyard';

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),pe.estate_id,pe.product_id,'invoice',CONCAT(pe.source_filename,':',pe.line_number),pe.source_filename,
  CONCAT_WS(' ',pe.package_size,pe.package_unit,'container'),pe.invoice_date,'needs_review',
  CONCAT_WS(' · ',pe.description,pe.notes)
FROM treatment_purchase_evidence pe WHERE pe.product_id IS NOT NULL
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),evidence_date=VALUES(evidence_date),notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_rate,observed_rate_unit,observed_water_l,evidence_date,verification_status,notes)
SELECT UUID(),a.estate_id,i.product_id,'historical_application',CONCAT(a.id,':',i.id),a.source_reference,
  i.dose_amount,i.dose_unit,a.water_volume_l,DATE(a.application_date),'historical_only',
  CONCAT_WS(' · ',a.purpose,i.notes,'Completed-use evidence does not establish current label eligibility or tank-mix compatibility.')
FROM spray_application_items i JOIN spray_applications a ON a.id=i.application_id
ON DUPLICATE KEY UPDATE observed_rate=VALUES(observed_rate),observed_rate_unit=VALUES(observed_rate_unit),observed_water_l=VALUES(observed_water_l),notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,notes)
SELECT UUID(),u.estate_id,u.product_id,'manufacturer_label',CONCAT('authorized-use:',u.id),u.label_url,u.label_verified_on,
  CASE WHEN u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE()) THEN 'verified'
       WHEN u.authorization_status='expired' OR u.authorization_expires_on<CURDATE() THEN 'expired' ELSE 'needs_review' END,
  CONCAT_WS(' · ',u.target_name,CONCAT_WS(' ',u.min_dose,'to',u.max_dose,u.dose_unit),u.notes)
FROM product_authorized_uses u
ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),evidence_date=VALUES(evidence_date),verification_status=VALUES(verification_status),notes=VALUES(notes);

INSERT INTO treatment_regulatory_sources (id,source_code,authority,source_scope,version_date,source_url,refresh_frequency,checked_on,notes)
VALUES
  (UUID(),'italy-plant-protection-open-data','Ministero della Salute','Complete national plant-protection product registry','2026-08-17','https://www.dati.salute.gov.it/it/dataset/fitosanitari/','weekly','2026-08-20','Product status and formulation source. Crop, target, dose, PHI and application instructions still require the latest authorized product label.'),
  (UUID(),'sicily-integrated-defense-2026-2','Regione Siciliana','2026 integrated-defense rules for crops and weed control','2026-05-21','https://regione.sicilia.it/la-regione-informa/difesa-fitosanitaria','as amended','2026-08-20','Regional active-substance limits supplement, but never replace, the product label and national authorization.'),
  (UUID(),'italy-organic-fertilizer-register','MASAF','Fertilizers recorded for conventional and organic agriculture',NULL,'https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/17462','periodic','2026-08-20','Fertilizer or biostimulant presence in the register does not by itself establish a vineyard foliar rate or tank-mix compatibility.')
ON DUPLICATE KEY UPDATE authority=VALUES(authority),source_scope=VALUES(source_scope),version_date=VALUES(version_date),source_url=VALUES(source_url),refresh_frequency=VALUES(refresh_frequency),checked_on=VALUES(checked_on),notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'official_register','ministry-open-data:2026-08-17:001583',
  'https://www.dati.salute.gov.it/it/dataset/fitosanitari/','WG · GRANULARE IDRODISPERSIBILE','2026-08-17','verified',
  'Exact Ministry match: registration 001583, MICROTHIOL DISPERSS, sulfur 80%, status Ri-registrato, authorization date through 2027-07-31.'
FROM products p WHERE p.name='MICROTHIOL DISPERSS'
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'official_register','ministry-open-data:2026-08-17:012759',
  'https://www.dati.salute.gov.it/it/dataset/fitosanitari/','WG · GRANULARE IDRODISPERSIBILE','2026-08-17','verified',
  'Exact Ministry match: registration 012759, OSSICLOR 35 WG, copper oxychloride 35%, status Ri-registrato, authorization date through 2029-06-30.'
FROM products p WHERE p.name='OSSICLOR 35 WG'
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'official_register','ministry-open-data:2026-08-17:012916',
  'https://www.dati.salute.gov.it/it/dataset/fitosanitari/','WG · GRANULARE IDRODISPERSIBILE','2026-08-17','needs_review',
  'Exact Ministry match: registration 012916, SACRON 45 WG, cymoxanil 45%. Snapshot contains an administrative date of 2026-08-15, while the estate owner confirms current authorization and in-date stock on 2026-08-20. Preserve this discrepancy for reconciliation; do not report the product as expired from this snapshot alone.'
FROM products p WHERE p.name='SACRON 45 WG'
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),evidence_date=VALUES(evidence_date),verification_status='needs_review',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'official_register','ministry-open-data:2026-08-17:no-exact-name-match',
  'https://www.dati.salute.gov.it/it/dataset/fitosanitari/','2026-08-17','needs_review',
  'No exact trade-name match was established in the Ministry plant-protection snapshot. This may be a fertilizer, corroborant, abbreviated trade name or a non-current product; capture the physical container label and registration details before eligibility is considered.'
FROM products p
WHERE p.name IN ('TERRAPLUS SOLUB NPK 8-7-6','FERTICUS 18 M')
ON DUPLICATE KEY UPDATE evidence_date=VALUES(evidence_date),verification_status='needs_review',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,observed_rate,observed_rate_unit,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'technical_product_page','technical-product-page:kalos-resolve-5kg',
  'https://www.agricolaalbese.it/kalos-resolve-biostimolante-5-kg-bio.html','water-dispersible powder · 5 kg',5,'g/L','2026-08-20','verified',
  'Kalos RESOLVE technical directions: vineyard foliar rate 5 g/L, minimum 2 kg/ha, 5 kg package. Product is mixed into treatment water; exact tank-mix compatibility remains subject to current directions, Agronomist approval and a compatibility test.'
FROM products p WHERE p.name='RESOLVE'
ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),observed_form=VALUES(observed_form),observed_rate=VALUES(observed_rate),observed_rate_unit=VALUES(observed_rate_unit),evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'owner_document','owner-confirmed:2026-08-20','Estate owner statement in operations task','2026-08-20','verified',
  'Estate owner confirms the product is authorized for estate use and the stock is not expired. This records estate authorization evidence separately from formulation, crop, dose, PHI, compatibility and official-register checks.'
FROM products p WHERE p.name IN ('FRONTIERE','SACRON 45 WG','REPENTE','IMPULSIVE PREMIUM','GEL DI SILICE','RESOLVE','MICROTHIOL DISPERSS','OSSICLOR 35 WG','OSSICLOR 20 BLU FLOW')
ON DUPLICATE KEY UPDATE evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,observed_rate,observed_rate_unit,observed_water_l,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'container_label',x.source_key,'User-supplied physical container photographs, 2026-08-20',x.observed_form,x.observed_rate,x.observed_rate_unit,x.observed_water_l,'2026-08-20','verified',x.notes
FROM products p JOIN (
  SELECT 'FRONTIERE' product_name,'container-label:frontiere-2.0' source_key,'liquid · 5 L' observed_form,NULL observed_rate,NULL observed_rate_unit,NULL observed_water_l,'K&A FRONTIERE 2.0: fluid organic nitrogen fertilizer; organic N 1%, biological organic carbon 10%, pH 4, organic matter <50kDa 30%; organic agriculture; store 4–30 C. Vineyard foliar rate is not visible.' notes UNION ALL
  SELECT 'SACRON 45 WG','container-label:sacron-45-wg','WG · 1 kg',NULL,NULL,NULL,'Cymoxanil 45%, FRAC 27, registration 012916, professional-use water-dispersible granules. Owner confirms authorized and in-date; latest full use label and registry discrepancy still require final review.' UNION ALL
  SELECT 'REPENTE','container-label:repente:lot-25642111E1','liquid · lot 25642111E1',1,'L/ha',NULL,'Vineyard foliar label range 1–3 L/ha; shake before use; use only for recognized need; jar-test compatibility especially with strong acids and alkaline products.' UNION ALL
  SELECT 'IMPULSIVE PREMIUM','container-label:impulsive-premium-f:lot-120751001C1','liquid · lot 120751001C1',2,'L/ha',NULL,'Fruit trees, olive and vine foliar label range 2–3 L/ha, from vegetative awakening throughout the crop cycle.' UNION ALL
  SELECT 'GEL DI SILICE','container-label:gel-di-silice:lot-26271001E2','gel/liquid · lot 26271001E2',100,'ml/100 L',100,'All-crop foliar label range 100–300 ml per 100 L water; compatibility test advised; do not mix with strong acids or bases; shake very well.' UNION ALL
  SELECT 'MICROTHIOL DISPERSS','container-label:microthiol-disperss','water-dispersible microgranules · 15 kg',NULL,NULL,NULL,'Sulfur 80%, FRAC M02, registration 001583; physical package confirms water-dispersible formulation and 15 kg pack.' UNION ALL
  SELECT 'OSSICLOR 20 BLU FLOW','container-label:ossiclor-20-blu-flow','SC liquid · 1 L',NULL,NULL,NULL,'Copper oxychloride suspension concentrate, 20 g/100 g, registration 012723, Manica; physical 1 L package.'
) x ON x.product_name=p.name
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),observed_rate=VALUES(observed_rate),observed_rate_unit=VALUES(observed_rate_unit),observed_water_l=VALUES(observed_water_l),verification_status='verified',notes=VALUES(notes);

INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'official_register','ministry-open-data:2026-08-17:012723','https://www.dati.salute.gov.it/it/dataset/fitosanitari/','SC · SOSPENSIONE CONCENTRATA','2026-08-17','verified',
  'Exact Ministry match: registration 012723, OSSICLOR 20 BLU FLOW, copper oxychloride 20%, Manica, status Ri-registrato, authorization date through 2029-06-30.'
FROM products p WHERE p.name='OSSICLOR 20 BLU FLOW'
ON DUPLICATE KEY UPDATE observed_form=VALUES(observed_form),evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes);

INSERT INTO equipment (id,estate_id,name,equipment_type,make_model,status,notes,active)
SELECT UUID(),e.id,'Cingo M8 tracked water sprayer','sprayer','Cingo M8','available',
  'User-confirmed water-spray application device. Tank capacity, nozzle configuration and calibration values must be measured from the actual unit before exact mix and coverage calculations.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM equipment q WHERE q.estate_id=e.id AND q.make_model='Cingo M8' AND q.equipment_type='sprayer');

INSERT INTO spray_equipment_profiles (id,estate_id,equipment_id,application_method,tank_capacity_l,calibration_status,source_reference,notes)
SELECT UUID(),q.estate_id,q.id,'water_spray',200,'needs_measurement',
  'User-supplied Cingo detachable sprayer-group brochure plus equipment image, received 2026-08-20.',
  'Brochure documents a nominal 200 L polyethylene tank. Record the actual usable fill, installed pump variant, nozzle setup, flow, pressure, travel speed and carrier L/ha after checking and calibrating the physical unit.'
FROM equipment q WHERE q.make_model='Cingo M8' AND q.equipment_type='sprayer'
ON DUPLICATE KEY UPDATE application_method='water_spray',tank_capacity_l=200,source_reference=VALUES(source_reference),notes=VALUES(notes),active=1;
