CREATE TABLE IF NOT EXISTS treatment_purchase_evidence (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NULL,
  invoice_date DATE NOT NULL,
  invoice_number VARCHAR(80) NOT NULL,
  supplier VARCHAR(180) NOT NULL,
  source_filename VARCHAR(255) NOT NULL,
  line_number SMALLINT UNSIGNED NOT NULL,
  description VARCHAR(500) NOT NULL,
  package_count DECIMAL(12,3) NULL,
  package_size DECIMAL(12,3) NULL,
  package_unit VARCHAR(30) NULL,
  quantity_total DECIMAL(12,3) NULL,
  quantity_unit VARCHAR(30) NULL,
  net_amount_eur DECIMAL(12,2) NULL,
  vat_rate_pct DECIMAL(6,2) NULL,
  treatment_relevance ENUM('candidate','support','not_treatment') NOT NULL DEFAULT 'candidate',
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_purchase_source_line (estate_id,source_filename,line_number),
  KEY ix_treatment_purchase_product_date (product_id,invoice_date),
  CONSTRAINT fk_treatment_purchase_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_purchase_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE spray_applications
SET status='cancelled',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[RESET 2026-08-19] The stale Treatment 5 date and copied Treatment 4 recipe were superseded by the evidence-based prescription engine. This is not a completed application. A new plan may be created only if current evidence supports it.'),
    agronomist_approved=0,label_legal_confirmed=0,phi_checked=0,rei_checked=0,weather_checked=0,ppe_confirmed=0,
    actual_details_confirmed=0
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND crop_scope='vineyard' AND LOWER(TRIM(purpose))='treatment 5' AND status='planned';

UPDATE products
SET name='MICROTHIOL DISPERSS',product_type='plant_protection',active_ingredient='Sulfur 80%',registration_number='001583',unit='kg',
    notes='Identity verified against the Italian Ministry product register and current manufacturer material on 2026-08-19.'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='MICROTHIOL DISPERS';

UPDATE products
SET product_type='plant_protection',active_ingredient='Copper oxychloride 35%',registration_number='012759',unit='kg',
    notes='Identity verified against the Italian Ministry product register and manufacturer label material on 2026-08-19.'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='OSSICLOR 35 WG';

UPDATE products
SET name='SACRON 45 WG',product_type='plant_protection',active_ingredient='Cymoxanil 45%',registration_number='012916',unit='kg',
    notes='Italian authorization expiry recorded as 2026-08-15 from the Ministry dataset refreshed 2026-08-17. Never recommend while expired.'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='SACRON 45';

UPDATE products SET product_type='fertilizer',unit='L' WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='IMPULSIVE PREMIUM';
UPDATE products SET product_type='fertilizer',unit='L',notes='Invoice records liquid 5 L packages. Historical source used a gram dose; exact container formulation and label must be verified before mixing.' WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='RESOLVE';
UPDATE products SET product_type='fertilizer',unit='kg',notes='Purchased as a 5 kg package. Historical source used a volume dose; exact product instructions and compatibility must be verified before mixing.' WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND name='GEL DI SILICE';

INSERT INTO products (id,estate_id,name,product_type,unit,supplier,notes,active)
SELECT UUID(),e.id,'TERRAPLUS SOLUB NPK 8-7-6','fertilizer','kg','AGRIPLANET S.R.L.','Purchased in 2026. Nutritional product; it is not automatically selected for disease control.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE product_type='fertilizer',unit='kg',supplier='AGRIPLANET S.R.L.',active=1;

INSERT INTO product_authorized_uses (
  id,estate_id,product_id,crop_scope,target_code,target_name,authorization_status,authorization_expires_on,
  label_verified_on,label_url,min_dose,max_dose,dose_unit,phi_days,max_applications,minimum_interval_days,
  resistance_group,growth_stage_limits,environmental_restrictions,notes,active
)
SELECT UUID(),e.id,p.id,'vineyard','powdery_mildew','Powdery mildew','authorized','2027-07-31','2026-08-19',
  'https://www.uplitalia.com/it/prodotto/3',2,12.5,'kg/ha',0,16,5,'M02',NULL,
  'Use only under the current label. Confirm crop condition, temperature, spray window, PPE and compatibility before approval.',
  'Wine/table grape label range: 2-4 kg/ha low pressure, 4-8 medium/severe, 8-12.5 severe/eradicant; maximum 125 kg/ha/year.',1
FROM estates e JOIN products p ON p.estate_id=e.id AND p.name='MICROTHIOL DISPERSS' WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE authorization_status='authorized',authorization_expires_on='2027-07-31',label_verified_on='2026-08-19',
  label_url=VALUES(label_url),min_dose=2,max_dose=12.5,dose_unit='kg/ha',phi_days=0,max_applications=16,minimum_interval_days=5,
  resistance_group='M02',environmental_restrictions=VALUES(environmental_restrictions),notes=VALUES(notes),active=1;

INSERT INTO product_authorized_uses (
  id,estate_id,product_id,crop_scope,target_code,target_name,authorization_status,authorization_expires_on,
  label_verified_on,label_url,min_dose,max_dose,dose_unit,phi_days,max_applications,resistance_group,
  environmental_restrictions,notes,active
)
SELECT UUID(),e.id,p.id,'vineyard','downy_mildew','Downy mildew','authorized','2029-06-30','2026-08-19',
  'https://www.manica.com/prodotti/ossicloruro-di-rame-ossiclor-35-wg/',1.4,3.4,'kg/ha',21,8,'M01',
  'Use only under the current label; observe copper limits, crop stage, PHI, weather, PPE and local restrictions.',
  'Manufacturer range for grape downy mildew/antracnose: 140-340 g/hL and 1.4-3.4 kg/ha; maximum 17 kg product/ha/year.',1
FROM estates e JOIN products p ON p.estate_id=e.id AND p.name='OSSICLOR 35 WG' WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE authorization_status='authorized',authorization_expires_on='2029-06-30',label_verified_on='2026-08-19',
  label_url=VALUES(label_url),min_dose=1.4,max_dose=3.4,dose_unit='kg/ha',phi_days=21,max_applications=8,
  resistance_group='M01',environmental_restrictions=VALUES(environmental_restrictions),notes=VALUES(notes),active=1;

INSERT INTO product_authorized_uses (
  id,estate_id,product_id,crop_scope,target_code,target_name,authorization_status,authorization_expires_on,
  label_verified_on,label_url,min_dose,max_dose,dose_unit,phi_days,max_applications,minimum_interval_days,
  resistance_group,growth_stage_limits,environmental_restrictions,notes,active
)
SELECT UUID(),e.id,p.id,'vineyard','downy_mildew','Downy mildew','expired','2026-08-15','2026-08-19',
  'https://uplitalia.com/it/prodotto/36',0.27,0.27,'kg/ha',28,4,7,'27','3-4 true leaves through veraison',
  'Expired authorization in the Ministry dataset. Do not recommend or apply unless a later official authorization is verified.',
  'Purchased in 2026, but purchase does not override authorization status or the 28-day wine-grape PHI.',1
FROM estates e JOIN products p ON p.estate_id=e.id AND p.name='SACRON 45 WG' WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE authorization_status='expired',authorization_expires_on='2026-08-15',label_verified_on='2026-08-19',
  label_url=VALUES(label_url),min_dose=.27,max_dose=.27,dose_unit='kg/ha',phi_days=28,max_applications=4,minimum_interval_days=7,
  resistance_group='27',growth_stage_limits=VALUES(growth_stage_limits),environmental_restrictions=VALUES(environmental_restrictions),notes=VALUES(notes),active=1;

INSERT INTO treatment_purchase_evidence (
  id,estate_id,product_id,invoice_date,invoice_number,supplier,source_filename,line_number,description,
  package_count,package_size,package_unit,quantity_total,quantity_unit,net_amount_eur,vat_rate_pct,treatment_relevance,notes
)
SELECT x.id,e.id,p.id,x.invoice_date,x.invoice_number,'AGRIPLANET S.R.L.',x.source_filename,x.line_number,x.description,
  x.package_count,x.package_size,x.package_unit,x.quantity_total,x.quantity_unit,x.net_amount,x.vat_rate,x.relevance,x.notes
FROM estates e
JOIN (
  SELECT '20260530-1478-0000-8000-000000000001' id,'2026-05-30' invoice_date,'1478' invoice_number,'IT016417907022026s_05pSf.xml' source_filename,1 line_number,'FUSTO IN PL. B/L LT. 50' description,2 package_count,50 package_size,'L' package_unit,100 quantity_total,'L' quantity_unit,36.07 net_amount,22 vat_rate,'not_treatment' relevance,'Two empty 50 L plastic drums; retained only for invoice reconciliation.' notes,NULL product_name UNION ALL
  SELECT '20260530-1478-0000-8000-000000000002','2026-05-30','1478','IT016417907022026s_05pSf.xml',2,'SACRON 45 WG KG 1 CIMOXANIL45%',1,1,'kg',1,'kg',18.18,10,'candidate','Purchase evidence only; current authorization still controls use.','SACRON 45 WG' UNION ALL
  SELECT '20260530-1478-0000-8000-000000000007','2026-05-30','1478','IT016417907022026s_05pSf.xml',7,'OSSICLOR 35 WG KG. 10 BIO ossicloruro di rame',1,10,'kg',10,'kg',69.55,10,'candidate','Purchase evidence only; current label and agronomic need still control use.','OSSICLOR 35 WG' UNION ALL
  SELECT '20260630-1919-0000-8000-000000000001','2026-06-30','1919','IT016417907022026V_06wJH.xml',1,'IMPULSIVE LT 1 CONSENTITO IN AGRICOLTURA BIOLOGICA',5,1,'L',5,'L',82.69,4,'support','Biostimulant/nutritional support; not direct disease control.','IMPULSIVE PREMIUM' UNION ALL
  SELECT '20260630-1919-0000-8000-000000000002','2026-06-30','1919','IT016417907022026V_06wJH.xml',2,'RESOLVE X 5 LT CONSENTITO IN AGRICOLTURA BIOLOGICA',1,5,'L',5,'L',79.81,4,'support','Combined with invoice line 4 for 10 L purchased. Exact formulation/label must be checked.','RESOLVE' UNION ALL
  SELECT '20260630-1919-0000-8000-000000000003','2026-06-30','1919','IT016417907022026V_06wJH.xml',3,'TERRAPLUS SOLUB NPK 8-7-6 15 KG CONSENTITO IN AGRICOLTURA BIOLOGICA',1,15,'kg',15,'kg',55.77,4,'support','Nutritional product; not direct disease control.','TERRAPLUS SOLUB NPK 8-7-6' UNION ALL
  SELECT '20260630-1919-0000-8000-000000000004','2026-06-30','1919','IT016417907022026V_06wJH.xml',4,'RESOLVE X 5 LT CONSENTITO IN AGRICOLTURA BIOLOGICA',1,5,'L',5,'L',79.81,4,'support','Combined with invoice line 2 for 10 L purchased. Exact formulation/label must be checked.','RESOLVE' UNION ALL
  SELECT '20260630-1919-0000-8000-000000000005','2026-06-30','1919','IT016417907022026V_06wJH.xml',5,'GEL DI SILICE X 5 KG CONSENTITO IN AGRICOLTURA BIOLOGICA',1,5,'kg',5,'kg',49.18,22,'support','Support product; container directions and tank compatibility must be confirmed.','GEL DI SILICE'
) x
LEFT JOIN products p ON p.estate_id=e.id AND p.name=x.product_name
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),description=VALUES(description),package_count=VALUES(package_count),
  package_size=VALUES(package_size),package_unit=VALUES(package_unit),quantity_total=VALUES(quantity_total),quantity_unit=VALUES(quantity_unit),
  net_amount_eur=VALUES(net_amount_eur),vat_rate_pct=VALUES(vat_rate_pct),treatment_relevance=VALUES(treatment_relevance),notes=VALUES(notes);
