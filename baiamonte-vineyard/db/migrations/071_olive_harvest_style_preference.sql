CREATE TABLE IF NOT EXISTS olive_harvest_preferences (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  record_year SMALLINT UNSIGNED NOT NULL,
  style_code ENUM('green_priority','green_balanced','estate_calendar') NOT NULL,
  notes TEXT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_olive_harvest_preference_year (estate_id,record_year),
  CONSTRAINT fk_olive_harvest_preference_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Owner direction received 2026-08-20: prefer a greener harvest prediction.
-- The dates remain model-derived from exact Baiamonte history and are not fixed here.
INSERT INTO olive_harvest_preferences (id,estate_id,record_year,style_code,notes,updated_by)
SELECT UUID(),e.id,2026,'green_priority',
  'Prefer a greener olive harvest; confirm representative fruit maturity, healthy fruit, weather and same-day mill capacity before picking.',
  'owner-confirmed preference'
FROM estates e
WHERE e.id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE record_year=VALUES(record_year);
