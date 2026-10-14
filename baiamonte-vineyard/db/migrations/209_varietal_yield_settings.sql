CREATE TABLE IF NOT EXISTS varietal_yield_settings (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  variety_id CHAR(36) NOT NULL,
  expected_finished_wine_l_per_kg DECIMAL(8,4) NOT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_varietal_yield_estate_variety (estate_id,variety_id),
  CONSTRAINT fk_varietal_yield_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_varietal_yield_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE CASCADE,
  CONSTRAINT chk_varietal_yield_positive CHECK (expected_finished_wine_l_per_kg > 0 AND expected_finished_wine_l_per_kg <= 1.2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

