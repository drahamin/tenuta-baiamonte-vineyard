ALTER TABLE spray_applications
  ADD COLUMN IF NOT EXISTS crop_scope ENUM('vineyard','olives') NOT NULL DEFAULT 'vineyard' AFTER season_id;

UPDATE spray_applications SET crop_scope='vineyard' WHERE crop_scope IS NULL;

UPDATE olive_records
SET record_date='2025-11-08',mill_date=COALESCE(mill_date,'2025-11-08'),
    evidence=CONCAT_WS('\n',NULLIF(evidence,''),'BAIAMONTE 2024-2026 · 2025 LAVORI ESEGUITI A BAIA MONTE row 62: RACCOLTA OLIVE 2025, 1,162 kg, 2025-11-08.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND record_year=2025 AND olives_harvested_kg=1162 AND record_date IS NULL;

INSERT INTO olive_records (
  id,estate_id,source_record_id,record_year,record_date,activity,details,status,
  olives_harvested_kg,mill_date,notes,evidence
)
SELECT
  '20251108-0000-4000-8000-000000000001',e.id,'OLIVE-2025-WORKBOOK-HARVEST',2025,'2025-11-08',
  'Olive harvest','RACCOLTA OLIVE 2025 · 9 workers plus truck · 1,162 kg.','workbook actual',
  1162,'2025-11-08','Exact harvest date and weight retained as historical forecasting evidence.',
  'BAIAMONTE 2024-2026 · 2025 LAVORI ESEGUITI A BAIA MONTE row 62, 2025-11-08.'
FROM estates e
WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (
    SELECT 1 FROM olive_records r
    WHERE r.estate_id=e.id AND r.record_year=2025 AND r.olives_harvested_kg=1162
  );

CREATE TABLE IF NOT EXISTS product_authorized_uses (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  crop_scope ENUM('vineyard','olives') NOT NULL,
  target_code VARCHAR(100) NOT NULL,
  target_name VARCHAR(180) NOT NULL,
  authorization_status ENUM('authorized','suspended','expired','unknown') NOT NULL DEFAULT 'unknown',
  authorization_expires_on DATE NULL,
  label_verified_on DATE NULL,
  label_url TEXT NULL,
  min_dose DECIMAL(12,3) NULL,
  max_dose DECIMAL(12,3) NULL,
  dose_unit VARCHAR(40) NULL,
  phi_days SMALLINT UNSIGNED NULL,
  rei_hours SMALLINT UNSIGNED NULL,
  max_applications SMALLINT UNSIGNED NULL,
  minimum_interval_days SMALLINT UNSIGNED NULL,
  resistance_group VARCHAR(80) NULL,
  growth_stage_limits VARCHAR(255) NULL,
  environmental_restrictions TEXT NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_product_authorized_use (estate_id,product_id,crop_scope,target_code),
  KEY ix_product_use_candidate (estate_id,crop_scope,target_code,authorization_status,active),
  CONSTRAINT fk_product_use_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_product_use_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE VIEW v_treatment_history AS
SELECT a.id,a.estate_id,a.crop_scope,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
       a.operator_name,a.planned_by,a.assigned_to,a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,
       a.source_products,a.source_doses,a.source_water_text,a.source_method,a.source_instructions,a.source_reference,
       b.code block_code,b.name block_name,
       a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
       a.ppe_confirmed,a.actual_details_confirmed,
       COALESCE(
         GROUP_CONCAT(CONCAT(p.name,' ',i.dose_amount,' ',i.dose_unit) ORDER BY p.name SEPARATOR ' | '),
         REPLACE(a.source_products,'\n',' | ')
       ) products,
       MAX(i.phi_days) phi_days
FROM spray_applications a
LEFT JOIN vineyard_blocks b ON b.id=a.block_id
LEFT JOIN spray_application_items i ON i.application_id=a.id
LEFT JOIN products p ON p.id=i.product_id
GROUP BY a.id,a.estate_id,a.crop_scope,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
         a.operator_name,a.planned_by,a.assigned_to,a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,
         a.source_products,a.source_doses,a.source_water_text,a.source_method,a.source_instructions,a.source_reference,
         b.code,b.name,a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
         a.ppe_confirmed,a.actual_details_confirmed;

INSERT INTO products (id,estate_id,name,product_type,unit,notes,active)
SELECT UUID(),e.id,'FERTICUS 18 M','fertilizer','g','Recorded in owner-supplied olive treatment sheet dated 2026-05-11; composition and current label eligibility require verification.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE active=1;

INSERT INTO products (id,estate_id,name,product_type,unit,notes,active)
SELECT UUID(),e.id,'IMPULSIVE PREMIUM','plant_protection','ml','Recorded in owner-supplied olive treatment sheet dated 2026-05-11; active ingredient and current label eligibility require verification.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE active=1;

INSERT INTO products (id,estate_id,name,product_type,unit,notes,active)
SELECT UUID(),e.id,'GEL DI SILICE','fertilizer','ml','Recorded in owner-supplied olive treatment sheet dated 2026-05-11; composition and current label eligibility require verification.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE active=1;

INSERT INTO spray_applications (
  id,estate_id,season_id,crop_scope,application_date,planned_application_date,purpose,
  water_volume_l,status,notes,source_application_id,evidence_status,actual_details_confirmed,
  agronomist_approved,label_legal_confirmed,phi_checked,rei_checked,weather_checked,ppe_confirmed,
  source_products,source_doses,source_water_text,source_reference
)
SELECT
  '20260511-0000-4000-8000-000000000001',e.id,s.id,'olives','2026-05-11 08:00:00','2026-05-11',
  'Olive treatment 1/2026',200,'completed',
  'Owner confirmed this treatment was completed. Product names, dose basis and water volume are confirmed by the supplied treatment sheet; target and safety approvals are not present in the source.',
  'OWNER-OLIVE-TREATMENT-2026-01','owner_confirmed_document',1,0,0,0,0,0,0,
  'FERTICUS 18 M\nIMPULSIVE PREMIUM\nGEL DI SILICE',
  'FERTICUS 18 M: 600 g/100 L (1,200 g total)\nIMPULSIVE PREMIUM: 150 ml/100 L (300 ml total)\nGEL DI SILICE: 100 ml/100 L (200 ml total)',
  '200 L','Owner-supplied TRATTAMENTO OLIVE TENUTA BAIAMONTE.JPG, received 2026-08-19.'
FROM estates e
LEFT JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE crop_scope='olives',application_date=VALUES(application_date),planned_application_date=VALUES(planned_application_date),
  purpose=VALUES(purpose),water_volume_l=VALUES(water_volume_l),status='completed',notes=VALUES(notes),evidence_status=VALUES(evidence_status),
  actual_details_confirmed=1,source_products=VALUES(source_products),source_doses=VALUES(source_doses),source_water_text=VALUES(source_water_text),source_reference=VALUES(source_reference);

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),'20260511-0000-4000-8000-000000000001',p.id,600,'g/100 L',1200,'200 L water; total calculated from the recorded per-100-L dose.'
FROM products p JOIN estates e ON e.id=p.estate_id WHERE e.slug='tenuta-baiamonte' AND p.name='FERTICUS 18 M';

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),'20260511-0000-4000-8000-000000000001',p.id,150,'ml/100 L',300,'200 L water; total calculated from the recorded per-100-L dose.'
FROM products p JOIN estates e ON e.id=p.estate_id WHERE e.slug='tenuta-baiamonte' AND p.name='IMPULSIVE PREMIUM';

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),'20260511-0000-4000-8000-000000000001',p.id,100,'ml/100 L',200,'200 L water; total calculated from the recorded per-100-L dose.'
FROM products p JOIN estates e ON e.id=p.estate_id WHERE e.slug='tenuta-baiamonte' AND p.name='GEL DI SILICE';

INSERT INTO spray_applications (
  id,estate_id,season_id,crop_scope,application_date,planned_application_date,purpose,status,notes,
  source_application_id,evidence_status,actual_details_confirmed,agronomist_approved,label_legal_confirmed,
  phi_checked,rei_checked,weather_checked,ppe_confirmed,source_reference
)
SELECT '20250512-0000-4000-8000-000000000001',e.id,s.id,'olives','2025-05-12 08:00:00','2025-05-12',
  'Olive treatment 2/2025','completed','Historical completed work; product, dose, target and safety details are not present in the workbook row.',
  'WORKBOOK-OLIVE-TREATMENT-2025-02','workbook_source_unverified_details',0,0,0,0,0,0,0,
  'BAIAMONTE 2024-2026 · 2025 LAVORI ESEGUITI A BAIA MONTE row 36 · €180.'
FROM estates e LEFT JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2025 WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE crop_scope='olives',status='completed',source_reference=VALUES(source_reference);

INSERT INTO products (id,estate_id,name,product_type,unit,notes,active)
SELECT UUID(),e.id,n.name,'other',n.unit,'Owner-supplied 2026 vineyard treatment sheet; current legal label and product classification require verification.',1
FROM estates e
CROSS JOIN (
  SELECT 'MICROTHIOL DISPERS' name,'g' unit UNION ALL
  SELECT 'OSSICLOR 20 MANICA','g' UNION ALL
  SELECT 'REPENTE','ml' UNION ALL
  SELECT 'FRONTIERE','ml' UNION ALL
  SELECT 'SACRON 45','g' UNION ALL
  SELECT 'RESOLVE','g' UNION ALL
  SELECT 'OSSICLOR 35 WG','g'
) n
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE active=1;

UPDATE spray_applications
SET crop_scope='vineyard',application_date='2026-05-19 08:00:00',status='completed',actual_details_confirmed=1,
    water_volume_l=NULL,source_water_text='Prior treatment used 400 L; this treatment should use somewhat more. Exact volume not recorded.',
    source_products='MICROTHIOL DISPERS\nFERTICUS 18 M\nIMPULSIVE PREMIUM\nFRONTIERE\nSACRON 45',
    source_doses='MICROTHIOL DISPERS: 400 g/100 L\nFERTICUS 18 M: 350 g/100 L\nIMPULSIVE PREMIUM: 400 g/100 L\nFRONTIERE: 150 ml/100 L\nSACRON 45: 80 g/100 L',
    source_instructions='Applied across 2026-05-19 and 2026-05-20. Wet foliage well without product dripping.',
    source_reference='Owner-supplied TRATTAMENTO VIGNETO TENUTA BAIAMONTE.jpeg, received 2026-08-19.',
    evidence_status='owner_confirmed_document',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[SOURCE REPAIR 2026-08-19] Documented treatment 2 operation dates are 2026-05-19 and 2026-05-20. Product/dose details confirmed; exact water volume and safety approvals are not documented.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND LOWER(TRIM(purpose))='treatment 2';

UPDATE spray_applications
SET crop_scope='vineyard',application_date='2026-05-08 08:00:00',status='completed',actual_details_confirmed=1,
    water_volume_l=500,source_water_text='500 L',
    source_products='MICROTHIOL DISPERS\nOSSICLOR 20 MANICA\nIMPULSIVE PREMIUM\nREPENTE\nFRONTIERE\nSACRON 45',
    source_doses='MICROTHIOL DISPERS: 600 g/100 L (3,000 g total)\nOSSICLOR 20 MANICA: 400 g/100 L (2,000 g total)\nIMPULSIVE PREMIUM: 450 g/100 L (2,250 g total)\nREPENTE: 300 ml/100 L (1,500 ml total)\nFRONTIERE: 150 ml/100 L (750 ml total)\nSACRON 45: 80 g/100 L (400 g total)',
    source_instructions='Applied across 2026-05-08 and 2026-05-09. Wet foliage well without product dripping.',
    source_reference='Owner-supplied 1006..jpeg, received 2026-08-19.',evidence_status='owner_confirmed_document',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[SOURCE REPAIR 2026-08-19] Documented treatment 3 operation dates are 2026-05-08 and 2026-05-09. Product/dose and 500 L water details confirmed; safety approvals are not documented.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND LOWER(TRIM(purpose))='treatment 3';

UPDATE spray_applications
SET crop_scope='vineyard',application_date='2026-06-17 08:00:00',status='completed',actual_details_confirmed=1,
    water_volume_l=NULL,source_water_text='Prior treatment used 400 L; this treatment should use somewhat more. Exact volume not recorded.',
    source_products='RESOLVE\nMICROTHIOL DISPERS\nOSSICLOR 35 WG\nFRONTIERE\nREPENTE\nGEL DI SILICE',
    source_doses='RESOLVE: 500 g/100 L\nMICROTHIOL DISPERS: 450 g/100 L\nOSSICLOR 35 WG: 340 g/100 L\nFRONTIERE: 150 ml/100 L\nREPENTE: 300 ml/100 L\nGEL DI SILICE: 450 ml/100 L',
    source_instructions='Applied across 2026-06-17 and 2026-06-18. Wet foliage and grape clusters well without product dripping.',
    source_reference='Owner-supplied TRATTAMENTO VIGNETO TENUTA BAIAMONTE.jpg, received 2026-08-19.',evidence_status='owner_confirmed_document',
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[SOURCE REPAIR 2026-08-19] Documented treatment 4 operation dates are 2026-06-17 and 2026-06-18. Product/dose details confirmed; exact water volume and safety approvals are not documented.')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1) AND LOWER(TRIM(purpose))='treatment 4';

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),a.id,p.id,x.dose,x.dose_unit,x.total_used,x.notes
FROM spray_applications a
JOIN estates e ON e.id=a.estate_id AND e.slug='tenuta-baiamonte'
JOIN (
  SELECT 'MICROTHIOL DISPERS' product_name,600 dose,'g/100 L' dose_unit,3000 total_used,'500 L water; calculated total.' notes UNION ALL
  SELECT 'OSSICLOR 20 MANICA',400,'g/100 L',2000,'500 L water; calculated total.' UNION ALL
  SELECT 'IMPULSIVE PREMIUM',450,'g/100 L',2250,'500 L water; calculated total.' UNION ALL
  SELECT 'REPENTE',300,'ml/100 L',1500,'500 L water; calculated total.' UNION ALL
  SELECT 'FRONTIERE',150,'ml/100 L',750,'500 L water; calculated total.' UNION ALL
  SELECT 'SACRON 45',80,'g/100 L',400,'500 L water; calculated total.'
) x
JOIN products p ON p.estate_id=a.estate_id AND p.name=x.product_name
WHERE LOWER(TRIM(a.purpose))='treatment 3';

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),a.id,p.id,x.dose,x.dose_unit,NULL,'Exact water volume is not recorded, so total product use is not calculated.'
FROM spray_applications a
JOIN estates e ON e.id=a.estate_id AND e.slug='tenuta-baiamonte'
JOIN (
  SELECT 'MICROTHIOL DISPERS' product_name,400 dose,'g/100 L' dose_unit UNION ALL
  SELECT 'FERTICUS 18 M',350,'g/100 L' UNION ALL
  SELECT 'IMPULSIVE PREMIUM',400,'g/100 L' UNION ALL
  SELECT 'FRONTIERE',150,'ml/100 L' UNION ALL
  SELECT 'SACRON 45',80,'g/100 L'
) x
JOIN products p ON p.estate_id=a.estate_id AND p.name=x.product_name
WHERE LOWER(TRIM(a.purpose))='treatment 2';

INSERT IGNORE INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,notes)
SELECT UUID(),a.id,p.id,x.dose,x.dose_unit,NULL,'Exact water volume is not recorded, so total product use is not calculated.'
FROM spray_applications a
JOIN estates e ON e.id=a.estate_id AND e.slug='tenuta-baiamonte'
JOIN (
  SELECT 'RESOLVE' product_name,500 dose,'g/100 L' dose_unit UNION ALL
  SELECT 'MICROTHIOL DISPERS',450,'g/100 L' UNION ALL
  SELECT 'OSSICLOR 35 WG',340,'g/100 L' UNION ALL
  SELECT 'FRONTIERE',150,'ml/100 L' UNION ALL
  SELECT 'REPENTE',300,'ml/100 L' UNION ALL
  SELECT 'GEL DI SILICE',450,'ml/100 L'
) x
JOIN products p ON p.estate_id=a.estate_id AND p.name=x.product_name
WHERE LOWER(TRIM(a.purpose))='treatment 4';

INSERT INTO spray_applications (
  id,estate_id,season_id,crop_scope,application_date,planned_application_date,purpose,status,notes,
  source_application_id,evidence_status,actual_details_confirmed,agronomist_approved,label_legal_confirmed,
  phi_checked,rei_checked,weather_checked,ppe_confirmed,source_reference
)
SELECT '20250623-0000-4000-8000-000000000001',e.id,s.id,'olives','2025-06-23 08:00:00','2025-06-23',
  'Olive treatment 3/2025','completed','Historical completed work; product, dose, target and safety details are not present in the workbook row.',
  'WORKBOOK-OLIVE-TREATMENT-2025-03','workbook_source_unverified_details',0,0,0,0,0,0,0,
  'BAIAMONTE 2024-2026 · 2025 LAVORI ESEGUITI A BAIA MONTE row 47 · €180.'
FROM estates e LEFT JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2025 WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE crop_scope='olives',status='completed',source_reference=VALUES(source_reference);
