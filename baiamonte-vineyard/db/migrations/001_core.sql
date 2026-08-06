CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(80) PRIMARY KEY,
  applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS estates (
  id CHAR(36) PRIMARY KEY,
  slug VARCHAR(80) NOT NULL UNIQUE,
  name VARCHAR(160) NOT NULL,
  timezone VARCHAR(80) NOT NULL DEFAULT 'Europe/Rome',
  latitude DECIMAL(10,7) NULL,
  longitude DECIMAL(10,7) NULL,
  total_area_ha DECIMAL(10,3) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_settings (
  estate_id CHAR(36) NOT NULL,
  setting_key VARCHAR(120) NOT NULL,
  setting_value JSON NOT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id, setting_key),
  CONSTRAINT fk_settings_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS seasons (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  status ENUM('planning','active','harvest','cellar','closed') NOT NULL DEFAULT 'active',
  budbreak_date DATE NULL,
  harvest_start_date DATE NULL,
  harvest_end_date DATE NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_season_estate_year (estate_id, vintage_year),
  CONSTRAINT fk_season_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS grape_varieties (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(120) NOT NULL,
  color_hex CHAR(7) NULL,
  target_gdd DECIMAL(9,2) NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_variety_estate_name (estate_id, name),
  CONSTRAINT fk_variety_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vineyard_blocks (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  code VARCHAR(50) NOT NULL,
  name VARCHAR(140) NOT NULL,
  area_ha DECIMAL(10,3) NULL,
  planted_year SMALLINT UNSIGNED NULL,
  vine_count INT UNSIGNED NULL,
  row_count INT UNSIGNED NULL,
  row_spacing_m DECIMAL(6,2) NULL,
  vine_spacing_m DECIMAL(6,2) NULL,
  training_system VARCHAR(100) NULL,
  soil_type VARCHAR(160) NULL,
  elevation_m DECIMAL(8,2) NULL,
  aspect VARCHAR(40) NULL,
  irrigation_available TINYINT(1) NOT NULL DEFAULT 0,
  geometry_geojson JSON NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_block_estate_code (estate_id, code),
  CONSTRAINT fk_block_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS block_varieties (
  block_id CHAR(36) NOT NULL,
  variety_id CHAR(36) NOT NULL,
  area_ha DECIMAL(10,3) NULL,
  vine_count INT UNSIGNED NULL,
  clone VARCHAR(80) NULL,
  rootstock VARCHAR(80) NULL,
  PRIMARY KEY (block_id, variety_id),
  CONSTRAINT fk_bv_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE CASCADE,
  CONSTRAINT fk_bv_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS people (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(160) NOT NULL,
  role VARCHAR(100) NULL,
  email VARCHAR(190) NULL,
  phone VARCHAR(50) NULL,
  is_worker TINYINT(1) NOT NULL DEFAULT 0,
  active TINYINT(1) NOT NULL DEFAULT 1,
  notes TEXT NULL,
  CONSTRAINT fk_people_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NULL,
  title VARCHAR(220) NOT NULL,
  category VARCHAR(80) NOT NULL DEFAULT 'general',
  status ENUM('planned','in_progress','done','cancelled') NOT NULL DEFAULT 'planned',
  priority ENUM('low','normal','high','urgent') NOT NULL DEFAULT 'normal',
  due_date DATE NULL,
  assigned_person_id CHAR(36) NULL,
  estimated_hours DECIMAL(8,2) NULL,
  notes TEXT NULL,
  source VARCHAR(50) NOT NULL DEFAULT 'manual',
  completed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_tasks_due_status (estate_id, status, due_date),
  CONSTRAINT fk_task_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_task_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_task_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_task_person FOREIGN KEY (assigned_person_id) REFERENCES people(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_activities (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NULL,
  task_id CHAR(36) NULL,
  activity_date DATE NOT NULL,
  end_date DATE NULL,
  category VARCHAR(80) NOT NULL DEFAULT 'general',
  title VARCHAR(220) NOT NULL,
  status ENUM('planned','done','cancelled') NOT NULL DEFAULT 'done',
  labor_hours DECIMAL(9,2) NULL,
  worker_count SMALLINT UNSIGNED NULL,
  cost_eur DECIMAL(12,2) NULL,
  weather_note VARCHAR(255) NULL,
  notes TEXT NULL,
  source VARCHAR(50) NOT NULL DEFAULT 'manual',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_activity_date (estate_id, activity_date),
  CONSTRAINT fk_activity_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_activity_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_activity_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_activity_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS products (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(180) NOT NULL,
  product_type ENUM('plant_protection','fertilizer','fuel','cellar','packaging','other') NOT NULL DEFAULT 'other',
  active_ingredient VARCHAR(255) NULL,
  registration_number VARCHAR(100) NULL,
  unit VARCHAR(30) NOT NULL DEFAULT 'kg',
  reorder_level DECIMAL(12,3) NULL,
  supplier VARCHAR(180) NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_product_estate_name (estate_id, name),
  CONSTRAINT fk_product_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventory_movements (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  movement_date DATETIME(6) NOT NULL,
  movement_type ENUM('purchase','use','adjustment','waste','return') NOT NULL,
  quantity_delta DECIMAL(12,3) NOT NULL,
  unit_cost_eur DECIMAL(12,4) NULL,
  lot_number VARCHAR(100) NULL,
  expiry_date DATE NULL,
  reference_type VARCHAR(50) NULL,
  reference_id CHAR(36) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_inventory_product_date (product_id, movement_date),
  CONSTRAINT fk_inventory_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS spray_applications (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NULL,
  activity_id CHAR(36) NULL,
  application_date DATETIME(6) NOT NULL,
  purpose VARCHAR(180) NOT NULL,
  area_ha DECIMAL(10,3) NULL,
  water_volume_l DECIMAL(12,2) NULL,
  operator_name VARCHAR(160) NULL,
  equipment_name VARCHAR(160) NULL,
  temp_c DECIMAL(7,2) NULL,
  wind_kph DECIMAL(7,2) NULL,
  status ENUM('planned','completed','cancelled') NOT NULL DEFAULT 'completed',
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_spray_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_spray_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_spray_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_spray_activity FOREIGN KEY (activity_id) REFERENCES work_activities(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS spray_application_items (
  id CHAR(36) PRIMARY KEY,
  application_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  dose_amount DECIMAL(12,3) NOT NULL,
  dose_unit VARCHAR(40) NOT NULL,
  total_used DECIMAL(12,3) NULL,
  phi_days SMALLINT UNSIGNED NULL,
  notes TEXT NULL,
  CONSTRAINT fk_spray_item_application FOREIGN KEY (application_id) REFERENCES spray_applications(id) ON DELETE CASCADE,
  CONSTRAINT fk_spray_item_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS equipment (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(180) NOT NULL,
  equipment_type VARCHAR(100) NULL,
  make_model VARCHAR(160) NULL,
  serial_number VARCHAR(100) NULL,
  status ENUM('available','in_use','maintenance','retired') NOT NULL DEFAULT 'available',
  purchase_date DATE NULL,
  service_due_date DATE NULL,
  hours_or_km DECIMAL(12,1) NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_equipment_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS weather_stations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(160) NOT NULL,
  station_type ENUM('ecowitt','home_assistant','open_meteo','manual','other') NOT NULL,
  external_id VARCHAR(190) NULL,
  location_type ENUM('vineyard','cellar','other') NOT NULL DEFAULT 'vineyard',
  block_id CHAR(36) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  metadata JSON NULL,
  UNIQUE KEY uq_weather_station_external (estate_id, station_type, external_id),
  CONSTRAINT fk_station_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_station_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS weather_observations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  station_id CHAR(36) NULL,
  observed_at DATETIME(6) NOT NULL,
  temp_c DECIMAL(7,3) NULL,
  humidity_pct DECIMAL(7,3) NULL,
  pressure_hpa DECIMAL(9,3) NULL,
  wind_kph DECIMAL(8,3) NULL,
  wind_gust_kph DECIMAL(8,3) NULL,
  wind_direction_deg DECIMAL(7,2) NULL,
  rain_mm DECIMAL(10,3) NULL,
  solar_wm2 DECIMAL(9,2) NULL,
  uv_index DECIMAL(6,2) NULL,
  leaf_wetness_pct DECIMAL(7,3) NULL,
  soil_moisture_pct DECIMAL(7,3) NULL,
  soil_temp_c DECIMAL(7,3) NULL,
  source_hash CHAR(64) NULL,
  raw_payload JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_weather_station_time (station_id, observed_at),
  KEY ix_weather_estate_time (estate_id, observed_at),
  CONSTRAINT fk_weather_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_weather_station FOREIGN KEY (station_id) REFERENCES weather_stations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS weather_daily (
  estate_id CHAR(36) NOT NULL,
  station_id CHAR(36) NOT NULL,
  weather_date DATE NOT NULL,
  temp_min_c DECIMAL(7,3) NULL,
  temp_avg_c DECIMAL(7,3) NULL,
  temp_max_c DECIMAL(7,3) NULL,
  humidity_avg_pct DECIMAL(7,3) NULL,
  rain_mm DECIMAL(10,3) NULL,
  wind_max_kph DECIMAL(8,3) NULL,
  solar_mj_m2 DECIMAL(10,3) NULL,
  soil_moisture_avg_pct DECIMAL(7,3) NULL,
  gdd_base10 DECIMAL(9,3) NULL,
  et0_mm DECIMAL(9,3) NULL,
  PRIMARY KEY (station_id, weather_date),
  KEY ix_weather_daily_date (estate_id, weather_date),
  CONSTRAINT fk_weather_daily_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_weather_daily_station FOREIGN KEY (station_id) REFERENCES weather_stations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS phenology_observations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  block_id CHAR(36) NOT NULL,
  variety_id CHAR(36) NULL,
  observed_date DATE NOT NULL,
  stage_code VARCHAR(40) NOT NULL,
  stage_name VARCHAR(120) NULL,
  percent_complete DECIMAL(5,2) NULL,
  notes TEXT NULL,
  photo_url VARCHAR(500) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_phenology_block_date (block_id, observed_date),
  CONSTRAINT fk_pheno_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_pheno_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_pheno_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE CASCADE,
  CONSTRAINT fk_pheno_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scouting_observations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  issue_type VARCHAR(100) NOT NULL,
  severity ENUM('trace','low','medium','high','critical') NOT NULL DEFAULT 'low',
  incidence_pct DECIMAL(6,2) NULL,
  location_note VARCHAR(255) NULL,
  action_required TINYINT(1) NOT NULL DEFAULT 0,
  notes TEXT NULL,
  photo_url VARCHAR(500) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_scouting_block_date (block_id, observed_at),
  CONSTRAINT fk_scout_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_scout_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_scout_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS irrigation_events (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  ended_at DATETIME(6) NULL,
  volume_l DECIMAL(14,2) NULL,
  depth_mm DECIMAL(9,3) NULL,
  source ENUM('manual','automation','import') NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  CONSTRAINT fk_irrigation_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_irrigation_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_irrigation_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harvest_lots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  block_id CHAR(36) NULL,
  variety_id CHAR(36) NOT NULL,
  harvested_at DATETIME(6) NOT NULL,
  weight_kg DECIMAL(12,2) NULL,
  crate_count INT UNSIGNED NULL,
  avg_crate_kg DECIMAL(8,2) NULL,
  destination VARCHAR(160) NULL,
  brix DECIMAL(7,3) NULL,
  babo DECIMAL(7,3) NULL,
  ph DECIMAL(6,3) NULL,
  ta_g_l DECIMAL(7,3) NULL,
  condition_grade VARCHAR(40) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_harvest_season_date (season_id, harvested_at),
  CONSTRAINT fk_harvest_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_harvest_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_harvest_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_harvest_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cellar_containers (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  code VARCHAR(60) NOT NULL,
  name VARCHAR(160) NOT NULL,
  container_type ENUM('tank','barrel','amphora','demijohn','bin','other') NOT NULL DEFAULT 'tank',
  material VARCHAR(80) NULL,
  capacity_l DECIMAL(12,2) NOT NULL,
  location VARCHAR(120) NULL,
  sensor_entity_id VARCHAR(190) NULL,
  status ENUM('empty','in_use','cleaning','maintenance','retired') NOT NULL DEFAULT 'empty',
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_container_estate_code (estate_id, code),
  CONSTRAINT fk_container_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wine_lots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  code VARCHAR(80) NOT NULL,
  name VARCHAR(160) NOT NULL,
  stage ENUM('must','fermentation','malo','aging','bottled','closed') NOT NULL DEFAULT 'must',
  volume_l DECIMAL(12,2) NULL,
  variety_summary VARCHAR(255) NULL,
  current_container_id CHAR(36) NULL,
  started_at DATETIME(6) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_wine_lot_season_code (season_id, code),
  CONSTRAINT fk_wine_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_wine_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_wine_container FOREIGN KEY (current_container_id) REFERENCES cellar_containers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cellar_operations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  wine_lot_id CHAR(36) NULL,
  container_id CHAR(36) NULL,
  operation_at DATETIME(6) NOT NULL,
  operation_type VARCHAR(80) NOT NULL,
  amount DECIMAL(12,3) NULL,
  unit VARCHAR(30) NULL,
  product_id CHAR(36) NULL,
  temp_c DECIMAL(7,3) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_cellar_lot_date (wine_lot_id, operation_at),
  CONSTRAINT fk_cellarop_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellarop_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_cellarop_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL,
  CONSTRAINT fk_cellarop_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE SET NULL,
  CONSTRAINT fk_cellarop_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lab_samples (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  block_id CHAR(36) NULL,
  variety_id CHAR(36) NULL,
  wine_lot_id CHAR(36) NULL,
  sample_code VARCHAR(100) NULL,
  sample_name VARCHAR(180) NOT NULL,
  sample_type ENUM('grape','must','wine','soil','water','other') NOT NULL,
  sampled_at DATETIME(6) NULL,
  lab_date DATE NOT NULL,
  laboratory VARCHAR(160) NULL,
  source_document VARCHAR(500) NULL,
  needs_review TINYINT(1) NOT NULL DEFAULT 0,
  review_notes TEXT NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_lab_sample_date (estate_id, lab_date),
  CONSTRAINT fk_lab_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_lab_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_lab_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL,
  CONSTRAINT fk_lab_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lab_results (
  id CHAR(36) PRIMARY KEY,
  sample_id CHAR(36) NOT NULL,
  analyte_code VARCHAR(80) NOT NULL,
  analyte_name VARCHAR(160) NOT NULL,
  numeric_value DECIMAL(16,6) NULL,
  text_value VARCHAR(500) NULL,
  unit VARCHAR(50) NULL,
  method VARCHAR(160) NULL,
  min_reference DECIMAL(16,6) NULL,
  max_reference DECIMAL(16,6) NULL,
  flag ENUM('low','normal','high','review') NULL,
  UNIQUE KEY uq_lab_sample_analyte (sample_id, analyte_code),
  CONSTRAINT fk_result_sample FOREIGN KEY (sample_id) REFERENCES lab_samples(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS alerts (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  alert_type VARCHAR(80) NOT NULL,
  severity ENUM('info','warning','critical') NOT NULL DEFAULT 'warning',
  title VARCHAR(220) NOT NULL,
  message TEXT NOT NULL,
  source VARCHAR(80) NULL,
  source_id VARCHAR(100) NULL,
  status ENUM('open','acknowledged','resolved','dismissed') NOT NULL DEFAULT 'open',
  triggered_at DATETIME(6) NOT NULL,
  acknowledged_at DATETIME(6) NULL,
  resolved_at DATETIME(6) NULL,
  metadata JSON NULL,
  KEY ix_alert_status_date (estate_id, status, triggered_at),
  CONSTRAINT fk_alert_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notes (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  note_date DATETIME(6) NOT NULL,
  title VARCHAR(220) NULL,
  body TEXT NOT NULL,
  tags JSON NULL,
  related_type VARCHAR(50) NULL,
  related_id CHAR(36) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_note_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NULL,
  actor VARCHAR(160) NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id VARCHAR(100) NULL,
  before_data JSON NULL,
  after_data JSON NULL,
  occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_audit_estate_date (estate_id, occurred_at),
  CONSTRAINT fk_audit_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS integration_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NULL,
  integration_name VARCHAR(100) NOT NULL,
  direction ENUM('inbound','outbound') NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  external_id VARCHAR(190) NULL,
  status ENUM('received','processed','failed','ignored') NOT NULL DEFAULT 'received',
  payload JSON NULL,
  error_message TEXT NULL,
  occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_integration_status_date (integration_name, status, occurred_at),
  CONSTRAINT fk_integration_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO estates (id, slug, name, timezone)
VALUES ('00000000-0000-4000-8000-000000000001', 'tenuta-baiamonte', 'Tenuta Baiamonte', 'Europe/Rome');

INSERT IGNORE INTO seasons (id, estate_id, vintage_year, status)
VALUES (UUID(), '00000000-0000-4000-8000-000000000001', YEAR(CURDATE()), 'active');
