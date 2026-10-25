CREATE TABLE IF NOT EXISTS olive_harvest_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  record_year SMALLINT UNSIGNED NOT NULL,
  window_start DATE NOT NULL,
  window_end DATE NOT NULL,
  crew_lead VARCHAR(190) NULL,
  crew_description VARCHAR(500) NULL,
  crew_size SMALLINT UNSIGNED NULL,
  crate_capacity_kg DECIMAL(8,2) NOT NULL DEFAULT 15.00,
  planned_crop_kg DECIMAL(12,2) NULL,
  crew_capacity_crates_per_day DECIMAL(10,2) NULL,
  mill_status ENUM('not_confirmed','requested','confirmed') NOT NULL DEFAULT 'not_confirmed',
  notes TEXT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_olive_harvest_plan_year (estate_id,record_year),
  CONSTRAINT fk_olive_harvest_plan_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Owner planning update received 2026-10-25. Crop quantity and team headcount remain deliberately blank.
INSERT INTO olive_harvest_plans (
  id,estate_id,record_year,window_start,window_end,crew_lead,crew_description,
  crate_capacity_kg,mill_status,notes,updated_by
)
SELECT UUID(),e.id,2026,'2026-10-26','2026-11-01','Giancarlo','Giancarlo and team',
  15.00,'not_confirmed',
  'Owner expects olive picking next week using the 15 kg grape crates. Exact day, team count, crop estimate, maturity check, weather and mill appointment remain to be confirmed.',
  'owner planning update 2026-10-25'
FROM estates e
WHERE e.id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE
  window_start=VALUES(window_start),window_end=VALUES(window_end),crew_lead=VALUES(crew_lead),
  crew_description=VALUES(crew_description),crate_capacity_kg=VALUES(crate_capacity_kg),
  notes=VALUES(notes),updated_by=VALUES(updated_by);
