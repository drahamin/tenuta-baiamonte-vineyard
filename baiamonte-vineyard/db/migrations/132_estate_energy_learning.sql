CREATE TABLE IF NOT EXISTS estate_energy_observations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  pv_power_w DECIMAL(12,2) NULL,
  estate_load_w DECIMAL(12,2) NULL,
  battery_soc_pct DECIMAL(5,2) NULL,
  battery_power_w DECIMAL(12,2) NULL,
  grid_power_w DECIMAL(12,2) NULL,
  generator_power_w DECIMAL(12,2) NULL,
  forecast_remaining_kwh DECIMAL(10,3) NULL,
  evidence JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_estate_energy_observation_minute (estate_id,observed_at),
  KEY ix_estate_energy_time (estate_id,observed_at),
  CONSTRAINT fk_estate_energy_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO app_settings (estate_id,setting_key,setting_value)
SELECT id,'energy_management',JSON_OBJECT('mode','shadow','battery_capacity_kwh',10.24,
  'reserve_floor_pct',30,'critical_floor_pct',20,'recovery_target_pct',45,
  'automatic_control_enabled',FALSE,'approved_controllable_loads',JSON_ARRAY())
FROM estates ON DUPLICATE KEY UPDATE setting_value=setting_value;
