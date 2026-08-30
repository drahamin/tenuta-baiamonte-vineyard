CREATE TABLE IF NOT EXISTS worker_vehicle_observations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  person_entity VARCHAR(255) NOT NULL,
  worker_key VARCHAR(120) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  presence_status ENUM('present','absent','uncertain') NOT NULL DEFAULT 'uncertain',
  confidence_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
  vehicle_make VARCHAR(120) NULL,
  vehicle_model VARCHAR(120) NULL,
  vehicle_type VARCHAR(120) NULL,
  vehicle_color VARCHAR(80) NULL,
  frame_sha256 CHAR(64) NOT NULL,
  model_version VARCHAR(120) NULL,
  review_status ENUM('unreviewed','confirmed','rejected') NOT NULL DEFAULT 'unreviewed',
  evidence JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_worker_vehicle_frame (estate_id,person_entity,camera_entity_id,frame_sha256),
  KEY ix_worker_vehicle_person_time (estate_id,person_entity,observed_at),
  KEY ix_worker_vehicle_day (estate_id,worker_key,observed_at,presence_status),
  CONSTRAINT fk_worker_vehicle_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO app_settings (estate_id,setting_key,setting_value)
SELECT id,'people_profiles',JSON_OBJECT(
  'person.giancarlo',JSON_OBJECT(
    'vehicle_tracking_enabled',TRUE,'vehicle_make','Volkswagen','vehicle_model','Golf',
    'vehicle_type','hatchback','vehicle_color','silver','vehicle_camera_entity','camera.vineyard_north',
    'normal_work_days',JSON_ARRAY('mon','tue','wed','thu','fri','sat'),
    'normal_start_time','07:00','normal_end_time','14:00',
    'vehicles',JSON_ARRAY(JSON_OBJECT('make','Volkswagen','model','Golf','type','hatchback','color','silver'))
  ),
  'person.carmela',JSON_OBJECT(
    'vehicle_tracking_enabled',TRUE,'vehicle_make','Fiat','vehicle_model','Punto',
    'vehicle_type','car','vehicle_color','blue','vehicle_camera_entity','camera.vineyard_north',
    'vehicles',JSON_ARRAY(JSON_OBJECT('make','Fiat','model','Punto','type','car','color','blue'))
  ),
  'person.luca_schiliro_cognato',JSON_OBJECT(
    'vehicle_tracking_enabled',TRUE,'vehicle_make','Renault','vehicle_model','Kangoo',
    'vehicle_type','small van','vehicle_color','white','vehicle_camera_entity','camera.vineyard_north',
    'vehicles',JSON_ARRAY(
      JSON_OBJECT('make','Renault','model','Kangoo','type','small van','color','white'),
      JSON_OBJECT('make','Fiat','model','Panda','type','car','color','red','notes','older model')
    )
  )
FROM estates
ON DUPLICATE KEY UPDATE setting_value=JSON_SET(
  IF(JSON_VALID(setting_value),setting_value,JSON_OBJECT()),
  '$."person.giancarlo".vehicle_tracking_enabled',TRUE,
  '$."person.giancarlo".vehicle_make','Volkswagen',
  '$."person.giancarlo".vehicle_model','Golf',
  '$."person.giancarlo".vehicle_type','hatchback',
  '$."person.giancarlo".vehicle_color','silver',
  '$."person.giancarlo".vehicle_camera_entity','camera.vineyard_north',
  '$."person.giancarlo".normal_work_days',JSON_ARRAY('mon','tue','wed','thu','fri','sat'),
  '$."person.giancarlo".normal_start_time','07:00',
  '$."person.giancarlo".normal_end_time','14:00',
  '$."person.giancarlo".vehicles',JSON_ARRAY(JSON_OBJECT('make','Volkswagen','model','Golf','type','hatchback','color','silver')),
  '$."person.carmela".vehicle_tracking_enabled',TRUE,
  '$."person.carmela".vehicle_make','Fiat',
  '$."person.carmela".vehicle_model','Punto',
  '$."person.carmela".vehicle_type','car',
  '$."person.carmela".vehicle_color','blue',
  '$."person.carmela".vehicle_camera_entity','camera.vineyard_north',
  '$."person.carmela".vehicles',JSON_ARRAY(JSON_OBJECT('make','Fiat','model','Punto','type','car','color','blue')),
  '$."person.luca_schiliro_cognato".vehicle_tracking_enabled',TRUE,
  '$."person.luca_schiliro_cognato".vehicle_make','Renault',
  '$."person.luca_schiliro_cognato".vehicle_model','Kangoo',
  '$."person.luca_schiliro_cognato".vehicle_type','small van',
  '$."person.luca_schiliro_cognato".vehicle_color','white',
  '$."person.luca_schiliro_cognato".vehicle_camera_entity','camera.vineyard_north',
  '$."person.luca_schiliro_cognato".vehicles',JSON_ARRAY(
    JSON_OBJECT('make','Renault','model','Kangoo','type','small van','color','white'),
    JSON_OBJECT('make','Fiat','model','Panda','type','car','color','red','notes','older model')
  )
);
