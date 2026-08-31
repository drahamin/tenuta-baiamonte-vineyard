CREATE TABLE IF NOT EXISTS estate_security_cameras (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  display_name VARCHAR(180) NOT NULL,
  source_role ENUM('entry_exit','parking','doorbell','perimeter','supporting') NOT NULL DEFAULT 'supporting',
  direction_rule ENUM('none','front_right_entry','front_left_entry','toward_entry','away_entry') NOT NULL DEFAULT 'none',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  always_analyze TINYINT(1) NOT NULL DEFAULT 0,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_estate_security_camera (estate_id,camera_entity_id),
  KEY ix_estate_security_camera_enabled (estate_id,enabled,sort_order),
  CONSTRAINT fk_estate_security_camera_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS estate_vehicle_movements (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_key CHAR(64) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  camera_name VARCHAR(180) NOT NULL,
  observation_zone VARCHAR(80) NOT NULL DEFAULT 'estate',
  observed_at DATETIME(6) NOT NULL,
  movement_state ENUM('entry','exit','parked','passing','unknown') NOT NULL DEFAULT 'unknown',
  front_direction ENUM('left','right','toward_camera','away_from_camera','unclear') NOT NULL DEFAULT 'unclear',
  vehicle_index SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  vehicle_type VARCHAR(120) NULL,
  vehicle_make VARCHAR(120) NULL,
  vehicle_model VARCHAR(120) NULL,
  vehicle_color VARCHAR(80) NULL,
  license_plate VARCHAR(40) NULL,
  plate_country VARCHAR(80) NULL,
  plate_confidence_pct DECIMAL(5,2) NULL,
  staff_person_entity VARCHAR(255) NULL,
  staff_name VARCHAR(180) NULL,
  staff_match_confidence_pct DECIMAL(5,2) NULL,
  known_vehicle_id CHAR(36) NULL,
  subject_category ENUM('staff','contractor','visitor','delivery','service','unknown','other') NOT NULL DEFAULT 'unknown',
  tag_label VARCHAR(180) NULL,
  flagged TINYINT(1) NOT NULL DEFAULT 0,
  flag_reason VARCHAR(500) NULL,
  confidence_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
  edge_event_types JSON NULL,
  evidence_id CHAR(64) NULL,
  model_version VARCHAR(120) NULL,
  review_status ENUM('unreviewed','confirmed','rejected') NOT NULL DEFAULT 'unreviewed',
  reviewed_by VARCHAR(160) NULL,
  reviewed_at DATETIME(6) NULL,
  review_notes VARCHAR(1000) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_estate_vehicle_source (estate_id,source_key),
  KEY ix_estate_vehicle_day (estate_id,observed_at,movement_state),
  KEY ix_estate_vehicle_staff (estate_id,staff_person_entity,observed_at),
  KEY ix_estate_vehicle_plate (estate_id,license_plate,observed_at),
  KEY ix_estate_vehicle_review (estate_id,review_status,observed_at),
  CONSTRAINT fk_estate_vehicle_movement_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS estate_known_vehicles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  identity_key CHAR(64) NOT NULL,
  display_name VARCHAR(180) NOT NULL,
  vehicle_type VARCHAR(120) NULL,
  vehicle_make VARCHAR(120) NULL,
  vehicle_model VARCHAR(120) NULL,
  vehicle_color VARCHAR(80) NULL,
  license_plate VARCHAR(40) NULL,
  plate_country VARCHAR(80) NULL,
  person_entity VARCHAR(255) NULL,
  person_name VARCHAR(180) NULL,
  subject_category ENUM('staff','contractor','visitor','delivery','service','unknown','other') NOT NULL DEFAULT 'unknown',
  flagged TINYINT(1) NOT NULL DEFAULT 0,
  flag_reason VARCHAR(500) NULL,
  notes VARCHAR(1000) NULL,
  confirmed_observations INT UNSIGNED NOT NULL DEFAULT 1,
  first_seen_at DATETIME(6) NULL,
  last_seen_at DATETIME(6) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_estate_known_vehicle_identity (estate_id,identity_key),
  KEY ix_estate_known_vehicle_plate (estate_id,license_plate),
  KEY ix_estate_known_vehicle_person (estate_id,person_entity),
  KEY ix_estate_known_vehicle_active (estate_id,active,last_seen_at),
  CONSTRAINT fk_estate_known_vehicle_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO estate_security_cameras
  (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order)
SELECT UUID(),id,'camera.vineyard_north','Main Parking','parking','front_right_entry',1,1,10 FROM estates;

INSERT IGNORE INTO estate_security_cameras
  (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order)
SELECT UUID(),id,'camera.rear_gate','Rear Gate','entry_exit','toward_entry',1,0,20 FROM estates;

INSERT IGNORE INTO estate_security_cameras
  (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order)
SELECT UUID(),id,'camera.t8171t1025291b5f','Rear Gate 360','entry_exit','toward_entry',1,0,30 FROM estates;

INSERT IGNORE INTO estate_security_cameras
  (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order)
SELECT UUID(),id,'camera.top_vineyard_360','Rear Entrance Path 360','entry_exit','toward_entry',1,0,40 FROM estates;
