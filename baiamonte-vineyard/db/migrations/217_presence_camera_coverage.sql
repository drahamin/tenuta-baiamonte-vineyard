CREATE TABLE IF NOT EXISTS estate_vehicle_frame_checks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  frame_sha256 CHAR(64) NOT NULL,
  evidence_id CHAR(64) NULL,
  vehicle_visible TINYINT(1) NOT NULL DEFAULT 0,
  movement_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  source_kind ENUM('event','scheduled') NOT NULL DEFAULT 'scheduled',
  checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_estate_vehicle_frame (estate_id,camera_entity_id,frame_sha256),
  KEY ix_estate_vehicle_frame_camera (estate_id,camera_entity_id,checked_at),
  CONSTRAINT fk_estate_vehicle_frame_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO estate_security_cameras
  (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order)
SELECT UUID(),id,'camera.gate_doorbell_2','Front Gate Doorbell','doorbell','toward_entry',1,1,15 FROM estates
ON DUPLICATE KEY UPDATE
  display_name=VALUES(display_name),source_role=VALUES(source_role),direction_rule=VALUES(direction_rule),
  enabled=1,always_analyze=1,sort_order=VALUES(sort_order);

UPDATE estate_known_vehicles
SET identity_key=SHA2('person.giancarlo|silver|volkswagen|golf|hatchback',256),
    display_name='Giancarlo · silver Volkswagen Golf',vehicle_type='hatchback',
    vehicle_make='Volkswagen',vehicle_model='Golf',vehicle_color='silver',
    person_entity='person.giancarlo',person_name='Giancarlo Pafumi',subject_category='staff',
    notes='Recurring staff vehicle; corrected from a mismatched owner link on 2026-10-17.',active=1
WHERE id='16fceba8-4445-4fe0-b5e8-afd0783763e5';

UPDATE estate_vehicle_movements movement
JOIN estate_known_vehicles vehicle
  ON vehicle.estate_id=movement.estate_id
 AND vehicle.id='16fceba8-4445-4fe0-b5e8-afd0783763e5'
SET movement.staff_person_entity='person.giancarlo',movement.staff_name='Giancarlo Pafumi',
    movement.known_vehicle_id=vehicle.id,movement.subject_category='staff',
    movement.tag_label='Giancarlo · silver Volkswagen Golf',movement.review_status='confirmed',
    movement.reviewed_by='owner_confirmation',movement.reviewed_at=NOW(6),
    movement.review_notes='Owner confirmed Giancarlo silver Volkswagen Golf parked on 2026-10-17; no missed entry time was inferred.'
WHERE movement.camera_entity_id='camera.vineyard_north'
  AND movement.observed_at>='2026-10-17 00:00:00'
  AND LOWER(COALESCE(movement.vehicle_color,''))='silver'
  AND LOWER(COALESCE(movement.vehicle_type,''))='hatchback'
  AND movement.known_vehicle_id IS NULL;

INSERT IGNORE INTO estate_known_vehicles
  (id,estate_id,identity_key,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,
   person_entity,person_name,subject_category,notes,first_seen_at,last_seen_at,active)
SELECT UUID(),id,SHA2('person.nunzio_testa|blue|fiat|160|truck',256),
       'Nunzio · blue Fiat 160 truck','truck','Fiat','160','blue',
       'person.nunzio_testa','Nunzio Testa','staff','Recurring vehicle confirmed by the owner on 2026-10-17.',
       UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),1
FROM estates;

INSERT IGNORE INTO estate_known_vehicles
  (id,estate_id,identity_key,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,
   person_entity,person_name,subject_category,notes,first_seen_at,last_seen_at,active)
SELECT UUID(),id,SHA2('historical-rental|david|white|peugeot|4000|wagon|2026-09',256),
       'Historical rental · white Peugeot 4000 wagon','wagon','Peugeot','4000','white',
       'person.david_rahamin','David Rahamin','other',
       'Temporary rental used during the 45 days before 2026-10-17. Historical exclusion only; do not match to Giancarlo or treat as recurring.',
       DATE_SUB('2026-10-17 00:00:00',INTERVAL 45 DAY),'2026-10-17 00:00:00',0
FROM estates;
