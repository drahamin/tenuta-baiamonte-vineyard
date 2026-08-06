CREATE TABLE IF NOT EXISTS maturity_samples (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  block_id CHAR(36) NULL,
  variety_id CHAR(36) NULL,
  sampled_at DATETIME(6) NOT NULL,
  berry_count INT UNSIGNED NULL,
  sample_kg DECIMAL(9,3) NULL,
  brix DECIMAL(7,3) NULL,
  ph DECIMAL(6,3) NULL,
  ta_g_l DECIMAL(7,3) NULL,
  yan_mg_l DECIMAL(9,3) NULL,
  fruit_temp_c DECIMAL(7,3) NULL,
  disease_pct DECIMAL(6,2) NULL,
  condition_notes TEXT NULL,
  decision ENUM('monitor','resample','hold','ready','picked') NOT NULL DEFAULT 'monitor',
  provisional_pick_date DATE NULL,
  sampler VARCHAR(160) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_maturity_season_date (season_id, sampled_at),
  CONSTRAINT fk_maturity_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_maturity_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_maturity_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_maturity_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS lot_code VARCHAR(100) NULL AFTER season_id;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS planned_date DATE NULL AFTER harvested_at;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS planned_kg DECIMAL(12,2) NULL AFTER planned_date;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS gross_kg DECIMAL(12,2) NULL AFTER planned_kg;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS tare_kg DECIMAL(12,2) NULL AFTER gross_kg;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS fruit_temp_c DECIMAL(7,3) NULL AFTER avg_crate_kg;
ALTER TABLE harvest_lots ADD COLUMN IF NOT EXISTS status ENUM('provisional','ready','in_progress','received','reconciled','hold','cancelled') NOT NULL DEFAULT 'received' AFTER condition_grade;
CREATE UNIQUE INDEX IF NOT EXISTS uq_harvest_lot_code ON harvest_lots (estate_id, lot_code);

ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS harvest_lot_reference VARCHAR(120) NULL AFTER code;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS fruit_kg DECIMAL(12,3) NULL AFTER volume_l;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS initial_l DECIMAL(12,3) NULL AFTER fruit_kg;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS free_run_l DECIMAL(12,3) NULL AFTER initial_l;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS press_l DECIMAL(12,3) NULL AFTER free_run_l;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS loss_l DECIMAL(12,3) NULL AFTER press_l;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS lot_status VARCHAR(80) NULL AFTER stage;
ALTER TABLE wine_lots ADD COLUMN IF NOT EXISTS responsible VARCHAR(160) NULL AFTER started_at;
