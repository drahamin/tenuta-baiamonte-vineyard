-- Close the seven legacy safety-review cases without inventing evidence.
-- The completed applications remain authoritative history, but missing
-- contemporaneous checks make them permanently ineligible as prescriptions.

CREATE TABLE IF NOT EXISTS treatment_safety_dispositions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  application_id CHAR(36) NOT NULL,
  disposition ENUM('restricted_historical') NOT NULL,
  reviewed_by VARCHAR(190) NOT NULL,
  reviewed_at DATETIME(6) NOT NULL,
  basis TEXT NOT NULL,
  limitations_json JSON NOT NULL,
  safe_for_prediction_reuse TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_safety_disposition (estate_id,application_id),
  KEY ix_treatment_safety_disposition (estate_id,disposition),
  CONSTRAINT fk_treatment_safety_disposition_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_safety_disposition_application FOREIGN KEY (application_id) REFERENCES spray_applications(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO treatment_safety_dispositions
  (id,estate_id,application_id,disposition,reviewed_by,reviewed_at,basis,limitations_json,safe_for_prediction_reuse)
SELECT UUID(),a.estate_id,a.id,'restricted_historical','system-audit',CURRENT_TIMESTAMP(6),
  'Existing application sheets, product evidence, inventory reconciliation and owner confirmations were reviewed. The treatment is retained as completed history, but missing contemporaneous approval, PHI/REI, weather/PPE, calibration or exact-mixture evidence cannot be reconstructed after application. The case is closed as a historical restriction and may not be reused as a prescription.',
  CASE WHEN COALESCE(a.actual_details_confirmed,0)=0 THEN
    JSON_ARRAY('actual scope/operator details','contemporaneous agronomist approval','contemporaneous PHI/REI check','weather and PPE record','verified field calibration','exact mixture compatibility')
  ELSE
    JSON_ARRAY('contemporaneous agronomist approval','contemporaneous PHI/REI check','weather and PPE record','verified field calibration','exact mixture compatibility')
  END,
  0
FROM spray_applications a
WHERE a.status='completed'
  AND (COALESCE(a.actual_details_confirmed,0)=0 OR COALESCE(a.phi_checked,0)=0 OR COALESCE(a.agronomist_approved,0)=0)
ON DUPLICATE KEY UPDATE disposition=VALUES(disposition),reviewed_by=VALUES(reviewed_by),reviewed_at=VALUES(reviewed_at),
  basis=VALUES(basis),limitations_json=VALUES(limitations_json),safe_for_prediction_reuse=0;

CREATE OR REPLACE VIEW v_treatment_history AS
SELECT a.id,a.estate_id,a.crop_scope,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
       a.operator_name,a.planned_by,a.assigned_to,a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,
       a.source_products,a.source_doses,a.source_water_text,a.source_method,a.source_instructions,a.source_reference,
       b.code block_code,b.name block_name,
       a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
       a.ppe_confirmed,a.actual_details_confirmed,
       d.disposition safety_review_disposition,d.reviewed_by safety_reviewed_by,d.reviewed_at safety_reviewed_at,
       d.basis safety_review_basis,d.limitations_json safety_review_limitations,
       COALESCE(
         GROUP_CONCAT(CONCAT(p.name,' ',i.dose_amount,' ',i.dose_unit) ORDER BY p.name SEPARATOR ' | '),
         REPLACE(a.source_products,'\n',' | ')
       ) products,
       MAX(i.phi_days) phi_days
FROM spray_applications a
LEFT JOIN vineyard_blocks b ON b.id=a.block_id
LEFT JOIN spray_application_items i ON i.application_id=a.id
LEFT JOIN products p ON p.id=i.product_id
LEFT JOIN treatment_safety_dispositions d ON d.estate_id=a.estate_id AND d.application_id=a.id
GROUP BY a.id,a.estate_id,a.crop_scope,a.application_date,a.planned_application_date,a.purpose,a.area_ha,a.water_volume_l,
         a.operator_name,a.planned_by,a.assigned_to,a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,
         a.source_products,a.source_doses,a.source_water_text,a.source_method,a.source_instructions,a.source_reference,
         b.code,b.name,a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
         a.ppe_confirmed,a.actual_details_confirmed,d.disposition,d.reviewed_by,d.reviewed_at,d.basis,d.limitations_json;
