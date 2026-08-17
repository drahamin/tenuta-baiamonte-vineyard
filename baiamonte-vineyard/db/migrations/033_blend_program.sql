CREATE TABLE IF NOT EXISTS blend_program_settings (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT NOT NULL,
  blend_name VARCHAR(160) NOT NULL DEFAULT 'Nerello blend',
  nerello_variety_name VARCHAR(120) NOT NULL DEFAULT 'Nerello Mascalese',
  grenache_variety_name VARCHAR(120) NOT NULL DEFAULT 'Grenache',
  grecanico_variety_name VARCHAR(120) NOT NULL DEFAULT 'Grecanico',
  grenache_pct DECIMAL(7,3) NOT NULL DEFAULT 6.500,
  crate_weight_kg DECIMAL(8,3) NOT NULL DEFAULT 15.000,
  expected_yield_l_per_kg DECIMAL(8,4) NOT NULL DEFAULT 0.7000,
  tank_working_fill_pct DECIMAL(7,3) NOT NULL DEFAULT 90.000,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_blend_program_estate_vintage (estate_id, vintage_year),
  CONSTRAINT fk_blend_program_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO blend_program_settings (id,estate_id,vintage_year,updated_by)
SELECT UUID(),id,2026,'workbook-migration' FROM estates;
