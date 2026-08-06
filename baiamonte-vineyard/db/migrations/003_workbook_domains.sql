CREATE TABLE IF NOT EXISTS import_batches (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_name VARCHAR(255) NOT NULL,
  source_file_id VARCHAR(190) NULL,
  source_modified_at DATETIME(6) NULL,
  content_sha256 CHAR(64) NOT NULL,
  status ENUM('started','validated','committed','failed','rolled_back') NOT NULL DEFAULT 'started',
  row_count INT UNSIGNED NOT NULL DEFAULT 0,
  warning_count INT UNSIGNED NOT NULL DEFAULT 0,
  report JSON NULL,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  completed_at DATETIME(6) NULL,
  UNIQUE KEY uq_import_hash (estate_id, content_sha256),
  CONSTRAINT fk_import_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workbook_source_rows (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  import_batch_id CHAR(36) NOT NULL,
  sheet_name VARCHAR(160) NOT NULL,
  source_row_number INT UNSIGNED NOT NULL,
  row_values JSON NOT NULL,
  row_hash CHAR(64) NOT NULL,
  mapped_entity_type VARCHAR(80) NULL,
  mapped_entity_id VARCHAR(100) NULL,
  UNIQUE KEY uq_source_row (import_batch_id, sheet_name, source_row_number),
  KEY ix_source_row_hash (row_hash),
  CONSTRAINT fk_source_row_batch FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evidence_references (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  evidence_type ENUM('workbook','document','photo','email','whatsapp','calendar','user_confirmation','weather','other') NOT NULL,
  external_id VARCHAR(255) NULL,
  title VARCHAR(255) NULL,
  source_url VARCHAR(700) NULL,
  source_date DATETIME(6) NULL,
  confidence ENUM('authoritative','high','moderate','low','unverified') NOT NULL DEFAULT 'unverified',
  notes TEXT NULL,
  metadata JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_evidence_external (estate_id, evidence_type, external_id),
  CONSTRAINT fk_evidence_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_evidence (
  entity_type VARCHAR(80) NOT NULL,
  entity_id VARCHAR(100) NOT NULL,
  evidence_id CHAR(36) NOT NULL,
  relationship VARCHAR(80) NOT NULL DEFAULT 'supports',
  PRIMARY KEY (entity_type, entity_id, evidence_id),
  CONSTRAINT fk_entity_evidence_ref FOREIGN KEY (evidence_id) REFERENCES evidence_references(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cadastral_parcels (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  municipality VARCHAR(120) NOT NULL,
  cadastral_sheet VARCHAR(40) NOT NULL,
  parcel_number VARCHAR(40) NOT NULL,
  tenure VARCHAR(80) NULL,
  contract_protocol VARCHAR(160) NULL,
  tenure_start DATE NULL,
  tenure_end DATE NULL,
  cadastral_area_ha DECIMAL(12,4) NULL,
  conducted_area_ha DECIMAL(12,4) NULL,
  buildings_m2 DECIMAL(12,2) NULL,
  official_vineyard_area_ha DECIMAL(12,4) NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_parcel (estate_id, municipality, cadastral_sheet, parcel_number),
  CONSTRAINT fk_parcel_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vineyard_terraces (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  terrace_code VARCHAR(40) NOT NULL,
  cohort VARCHAR(120) NULL,
  training_system VARCHAR(80) NULL,
  allocated_vines INT UNSIGNED NULL,
  spacing_m DECIMAL(7,3) NULL,
  reconciliation_basis VARCHAR(255) NULL,
  confidence VARCHAR(80) NULL,
  field_census_status VARCHAR(80) NULL,
  live_vines INT UNSIGNED NULL,
  dead_missing_vines INT UNSIGNED NULL,
  replacement_new_vines INT UNSIGNED NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_terrace_estate_code (estate_id, terrace_code),
  CONSTRAINT fk_terrace_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nursery_deliveries (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  invoice_number VARCHAR(80) NULL,
  invoice_date DATE NULL,
  variety_id CHAR(36) NULL,
  supplied_variety_name VARCHAR(120) NOT NULL,
  quantity INT UNSIGNED NOT NULL,
  cohort_use VARCHAR(160) NULL,
  mapping_status VARCHAR(180) NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_nursery_delivery (estate_id, invoice_number, supplied_variety_name, quantity),
  CONSTRAINT fk_nursery_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_nursery_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS labor_entries (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NULL,
  person_id CHAR(36) NULL,
  source_labor_id VARCHAR(120) NULL,
  work_date DATE NULL,
  shift_label VARCHAR(100) NULL,
  person_or_crew VARCHAR(160) NOT NULL,
  role VARCHAR(100) NULL,
  regular_hours DECIMAL(9,2) NULL,
  overtime_hours DECIMAL(9,2) NULL,
  hourly_rate_eur DECIMAL(10,2) NULL,
  labor_cost_eur DECIMAL(12,2) NULL,
  kg_handled DECIMAL(12,2) NULL,
  incident_near_miss TINYINT(1) NOT NULL DEFAULT 0,
  approved_by VARCHAR(160) NULL,
  payment_status ENUM('unknown','unpaid','verification_needed','paid') NOT NULL DEFAULT 'unknown',
  payroll_scope ENUM('part_time','contractor','payroll_excluded','unknown') NOT NULL DEFAULT 'unknown',
  notes TEXT NULL,
  UNIQUE KEY uq_labor_source_id (estate_id, source_labor_id),
  CONSTRAINT fk_labor_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_labor_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE SET NULL,
  CONSTRAINT fk_labor_person FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS equipment_service_events (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  equipment_id CHAR(36) NULL,
  source_record_id VARCHAR(120) NULL,
  event_date DATE NOT NULL,
  asset_name VARCHAR(180) NOT NULL,
  pre_use_status VARCHAR(80) NULL,
  cleaning_started_at DATETIME(6) NULL,
  cleaning_ended_at DATETIME(6) NULL,
  sanitation_method TEXT NULL,
  concentration VARCHAR(80) NULL,
  released TINYINT(1) NULL,
  released_by VARCHAR(160) NULL,
  downtime_hours DECIMAL(9,2) NULL,
  maintenance_action TEXT NULL,
  next_due_date DATE NULL,
  notes TEXT NULL,
  UNIQUE KEY uq_equipment_source_id (estate_id, source_record_id),
  CONSTRAINT fk_service_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_service_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS issues_decisions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_issue_id VARCHAR(120) NULL,
  opened_date DATE NOT NULL,
  subject_ref VARCHAR(180) NULL,
  issue_type VARCHAR(80) NOT NULL,
  priority ENUM('low','medium','high','critical') NOT NULL DEFAULT 'medium',
  issue_text TEXT NOT NULL,
  evidence_summary MEDIUMTEXT NULL,
  decision_action MEDIUMTEXT NULL,
  owner_text VARCHAR(255) NULL,
  due_date DATE NULL,
  status ENUM('open','monitoring','resolved','deferred') NOT NULL DEFAULT 'open',
  closed_date DATE NULL,
  notes MEDIUMTEXT NULL,
  UNIQUE KEY uq_issue_source_id (estate_id, source_issue_id),
  CONSTRAINT fk_issue_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS harvest_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  source_plan_id VARCHAR(120) NULL,
  variety_id CHAR(36) NOT NULL,
  block_reference VARCHAR(120) NULL,
  planned_pick_date DATE NOT NULL,
  status ENUM('draft','provisional','confirmed','in_progress','complete','cancelled','hold') NOT NULL DEFAULT 'provisional',
  planned_kg DECIMAL(12,3) NULL,
  planned_crates INT UNSIGNED NULL,
  crew_size SMALLINT UNSIGNED NULL,
  planned_hours DECIMAL(9,2) NULL,
  cellar_destination VARCHAR(180) NULL,
  weather_risk VARCHAR(120) NULL,
  dependencies TEXT NULL,
  approved_by VARCHAR(160) NULL,
  confidence ENUM('low','medium','high') NULL,
  forecast_method VARCHAR(120) NULL,
  notes TEXT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_harvest_plan_source (estate_id, source_plan_id),
  CONSTRAINT fk_hplan_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_hplan_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_hplan_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gdd_forecasts (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  variety_id CHAR(36) NOT NULL,
  base_temp_c DECIMAL(6,2) NOT NULL DEFAULT 10,
  season_start DATE NOT NULL,
  target_gdd DECIMAL(10,3) NOT NULL,
  observed_through DATE NULL,
  observed_gdd DECIMAL(10,3) NULL,
  forecast_through DATE NULL,
  forecast_gdd DECIMAL(10,3) NULL,
  predicted_date DATE NULL,
  weather_adjustment_days SMALLINT NOT NULL DEFAULT 0,
  lab_adjustment_days SMALLINT NOT NULL DEFAULT 0,
  final_forecast_date DATE NULL,
  confidence ENUM('low','medium','high') NOT NULL DEFAULT 'low',
  calibration_evidence TEXT NULL,
  computed_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_gdd_forecast (season_id, variety_id, computed_at),
  CONSTRAINT fk_gdd_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_gdd_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_gdd_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fermentation_observations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NULL,
  source_observation_id VARCHAR(120) NULL,
  observed_at DATETIME(6) NOT NULL,
  vessel_name VARCHAR(160) NULL,
  stage VARCHAR(80) NULL,
  temp_c DECIMAL(7,3) NULL,
  density_sg DECIMAL(9,5) NULL,
  brix DECIMAL(7,3) NULL,
  ph DECIMAL(6,3) NULL,
  cap_management VARCHAR(180) NULL,
  addition_action TEXT NULL,
  product_lot VARCHAR(120) NULL,
  quantity DECIMAL(12,3) NULL,
  unit VARCHAR(40) NULL,
  sensory_observation TEXT NULL,
  owner_text VARCHAR(160) NULL,
  next_check_at DATETIME(6) NULL,
  status VARCHAR(80) NULL,
  UNIQUE KEY uq_fermentation_source (estate_id, source_observation_id),
  CONSTRAINT fk_fermentation_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_fermentation_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mass_balance_records (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  harvest_lot_reference VARCHAR(120) NOT NULL,
  block_reference VARCHAR(120) NULL,
  variety_name VARCHAR(120) NULL,
  net_grapes_kg DECIMAL(12,3) NULL,
  must_wine_l DECIMAL(12,3) NULL,
  free_run_l DECIMAL(12,3) NULL,
  press_l DECIMAL(12,3) NULL,
  recorded_loss_l DECIMAL(12,3) NULL,
  reconciliation_status VARCHAR(80) NULL,
  owner_text VARCHAR(160) NULL,
  notes TEXT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_mass_balance_reference (estate_id, harvest_lot_reference),
  CONSTRAINT fk_mass_balance_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS olive_records (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_record_id VARCHAR(120) NULL,
  record_year SMALLINT UNSIGNED NOT NULL,
  record_date DATE NULL,
  activity VARCHAR(100) NOT NULL,
  details MEDIUMTEXT NULL,
  status VARCHAR(80) NULL,
  worker_text VARCHAR(160) NULL,
  labor_hours DECIMAL(9,2) NULL,
  olives_harvested_kg DECIMAL(12,3) NULL,
  mill_date DATE NULL,
  oil_liters DECIMAL(12,3) NULL,
  yield_pct DECIMAL(7,3) NULL,
  notes MEDIUMTEXT NULL,
  evidence MEDIUMTEXT NULL,
  UNIQUE KEY uq_olive_source (estate_id, source_record_id),
  CONSTRAINT fk_olive_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vintage_summaries (
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  variety_name VARCHAR(120) NOT NULL,
  grapes_kg DECIMAL(12,3) NULL,
  wine_l DECIMAL(12,3) NULL,
  cassette_count DECIMAL(12,3) NULL,
  evidence_status VARCHAR(120) NULL,
  reconciliation_note TEXT NULL,
  PRIMARY KEY (estate_id, vintage_year, variety_name),
  CONSTRAINT fk_vintage_summary_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS source_application_id VARCHAR(120) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS evidence_status VARCHAR(120) NULL;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS actual_details_confirmed TINYINT(1) NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS uq_spray_source ON spray_applications (estate_id, source_application_id);
