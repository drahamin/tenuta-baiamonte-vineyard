CREATE TABLE IF NOT EXISTS vineyard_damage_assessments (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  event_key VARCHAR(120) NOT NULL,
  damage_type VARCHAR(80) NOT NULL,
  event_date DATE NOT NULL,
  assessed_at DATETIME(6) NOT NULL,
  observer_name VARCHAR(190) NOT NULL,
  trend ENUM('initial','worsening','stable','improving','resolved') NOT NULL DEFAULT 'initial',
  estate_yield_loss_pct DECIMAL(6,2) NULL,
  confidence ENUM('low','medium','high') NOT NULL DEFAULT 'low',
  review_status ENUM('draft','approved','rejected','archived') NOT NULL DEFAULT 'draft',
  approved_by VARCHAR(190) NULL,
  approved_at DATETIME(6) NULL,
  source_type VARCHAR(80) NOT NULL DEFAULT 'field_report',
  source_reference VARCHAR(255) NULL,
  evidence_json JSON NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_damage_assessment_event_date (estate_id,event_key,assessed_at),
  KEY ix_damage_assessment_current (estate_id,season_id,event_key,review_status,active,assessed_at),
  CONSTRAINT fk_damage_assessment_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_damage_assessment_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO vineyard_damage_assessments
  (id,estate_id,season_id,event_key,damage_type,event_date,assessed_at,observer_name,trend,estate_yield_loss_pct,confidence,review_status,approved_by,approved_at,source_type,source_reference,evidence_json,notes)
SELECT '79000000-0000-4000-8000-000000000001',s.estate_id,s.id,'hail-2026-06-27','hail','2026-06-27','2026-06-27 12:00:00','Sebastiano Vinci','initial',NULL,'low','approved','Sebastiano Vinci',CURRENT_TIMESTAMP(6),'photo_field_report','Owner-confirmed report dated 2026-06-27; six protected attachments',JSON_ARRAY(),'Initial hail damage report. Close-up photos do not establish an estate-wide loss percentage; enter a supported estimate when available.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE evidence_json=VALUES(evidence_json),notes=VALUES(notes),review_status='approved',approved_by='Sebastiano Vinci';

INSERT INTO vineyard_damage_assessments
  (id,estate_id,season_id,event_key,damage_type,event_date,assessed_at,observer_name,trend,estate_yield_loss_pct,confidence,review_status,approved_by,approved_at,source_type,source_reference,evidence_json,notes)
SELECT '79000000-0000-4000-8000-000000000002',s.estate_id,s.id,'hail-2026-06-27','hail','2026-06-27','2026-06-30 12:00:00','Sebastiano Vinci','worsening',NULL,'low','approved','Sebastiano Vinci',CURRENT_TIMESTAMP(6),'photo_field_report','Owner-confirmed follow-up dated 2026-06-30; four protected attachments',JSON_ARRAY(),'Follow-up showed damage still clearly visible and worse than the initial report. No unsupported estate-wide percentage is inferred from close-up photos.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE evidence_json=VALUES(evidence_json),notes=VALUES(notes),review_status='approved',approved_by='Sebastiano Vinci';

INSERT INTO vineyard_damage_assessments
  (id,estate_id,season_id,event_key,damage_type,event_date,assessed_at,observer_name,trend,estate_yield_loss_pct,confidence,review_status,approved_by,approved_at,source_type,source_reference,evidence_json,notes)
SELECT '79000000-0000-4000-8000-000000000003',s.estate_id,s.id,'hail-2026-06-27','hail','2026-06-27','2026-08-06 12:00:00','Giancarlo Pafumi','improving',NULL,'low','approved','Giancarlo Pafumi',CURRENT_TIMESTAMP(6),'photo_field_report','Owner-confirmed follow-up dated 2026-08-06; five protected attachments',JSON_ARRAY(),'Latest approved follow-up showed fuller clusters and uneven improvement. This report supersedes earlier estimates for forecasting without compounding them.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE evidence_json=VALUES(evidence_json),notes=VALUES(notes),review_status='approved',approved_by='Giancarlo Pafumi';
