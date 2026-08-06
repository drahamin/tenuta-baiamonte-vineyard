ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS planned_application_date DATE NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS planned_by VARCHAR(180) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(180) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_products MEDIUMTEXT NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_doses MEDIUMTEXT NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_water_text VARCHAR(255) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_method VARCHAR(255) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_instructions MEDIUMTEXT NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_reference MEDIUMTEXT NULL;

-- Backfill the authoritative treatment sheet from the already committed workbook
-- archive. This avoids asking the owner to re-import a file whose hash is correctly
-- protected against duplicate import.
INSERT INTO spray_applications (
  id,estate_id,season_id,application_date,planned_application_date,purpose,operator_name,status,notes,
  source_application_id,evidence_status,planned_by,assigned_to,source_products,source_doses,
  source_water_text,source_method,source_instructions,source_reference
)
SELECT
  UUID(),b.estate_id,s.id,
  TIMESTAMP(STR_TO_DATE(LEFT(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[2]')),''),JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[1]'))),10),'%Y-%m-%d'),'12:00:00'),
  STR_TO_DATE(LEFT(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[2]')),''),JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[1]'))),10),'%Y-%m-%d'),
  COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[7]')),''),CONCAT('Treatment ',JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[5]')))),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[14]')),
  'planned',
  CONCAT_WS('\n\n',NULLIF(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[20]')),''),CONCAT('Source status: ',COALESCE(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[15]')),'unknown'))),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[0]')),
  'source-reported, completion details need review',
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[13]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[14]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[8]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[9]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[10]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[11]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[19]')),
  JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[21]'))
FROM workbook_source_rows r
JOIN import_batches b ON b.id=r.import_batch_id AND b.status='committed'
JOIN seasons s ON s.estate_id=b.estate_id AND s.vintage_year=CAST(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[4]')) AS UNSIGNED)
WHERE r.sheet_name='Vineyard Treatments'
  AND JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[0]')) LIKE 'TRT-%'
  AND STR_TO_DATE(LEFT(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[2]')),''),JSON_UNQUOTE(JSON_EXTRACT(r.row_values,'$[1]'))),10),'%Y-%m-%d') IS NOT NULL
ON DUPLICATE KEY UPDATE
  planned_application_date=VALUES(planned_application_date),purpose=VALUES(purpose),operator_name=VALUES(operator_name),
  notes=VALUES(notes),planned_by=VALUES(planned_by),assigned_to=VALUES(assigned_to),source_products=VALUES(source_products),
  source_doses=VALUES(source_doses),source_water_text=VALUES(source_water_text),source_method=VALUES(source_method),
  source_instructions=VALUES(source_instructions),source_reference=VALUES(source_reference);

CREATE OR REPLACE VIEW v_treatment_history AS
SELECT a.id,a.estate_id,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
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
GROUP BY a.id,a.estate_id,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
         a.operator_name,a.planned_by,a.assigned_to,a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,
         a.source_products,a.source_doses,a.source_water_text,a.source_method,a.source_instructions,a.source_reference,
         b.code,b.name,a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
         a.ppe_confirmed,a.actual_details_confirmed;
