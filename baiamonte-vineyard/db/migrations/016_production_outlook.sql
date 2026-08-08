CREATE TABLE IF NOT EXISTS production_forecasts (
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  scenario VARCHAR(40) NOT NULL DEFAULT 'base',
  variety_name VARCHAR(120) NOT NULL,
  grape_kg DECIMAL(12,3) NOT NULL,
  crates_15kg INT UNSIGNED NOT NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'workbook',
  notes TEXT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id,vintage_year,scenario,variety_name),
  CONSTRAINT fk_production_forecast_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS grape_allocation_plans (
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  grape_name VARCHAR(120) NOT NULL,
  total_kg DECIMAL(12,3) NOT NULL,
  total_crates_15kg INT UNSIGNED NOT NULL,
  wine_destination VARCHAR(180) NOT NULL,
  blend_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
  blend_crates_15kg INT UNSIGNED NOT NULL DEFAULT 0,
  varietal_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
  varietal_crates_15kg INT UNSIGNED NOT NULL DEFAULT 0,
  field_instruction TEXT NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'workbook',
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id,vintage_year,grape_name),
  CONSTRAINT fk_grape_allocation_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wine_output_plans (
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  finished_wine VARCHAR(160) NOT NULL,
  composition VARCHAR(255) NOT NULL,
  grape_kg DECIMAL(12,3) NOT NULL,
  wine_l DECIMAL(12,3) NOT NULL,
  bottles_750ml INT UNSIGNED NOT NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'workbook',
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id,vintage_year,finished_wine),
  CONSTRAINT fk_wine_output_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO production_forecasts (estate_id,vintage_year,scenario,variety_name,grape_kg,crates_15kg,source) VALUES
('00000000-0000-4000-8000-000000000001',2026,'base','Grecanico',1833,123,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'base','Nerello Mascalese',2560,171,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'base','Grenache',470,32,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2027,'base','Grecanico',2929,196,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2027,'base','Nerello Mascalese',3285,219,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2027,'base','Grenache',795,53,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2028,'base','Grecanico',3478,232,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2028,'base','Nerello Mascalese',3386,226,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2028,'base','Grenache',972,65,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2029,'base','Grecanico',3919,262,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2029,'base','Nerello Mascalese',3471,232,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2029,'base','Grenache',1114,75,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2030,'base','Grecanico',3957,264,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2030,'base','Nerello Mascalese',3538,236,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2030,'base','Grenache',1123,75,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2031,'base','Grecanico',3957,264,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2031,'base','Nerello Mascalese',3538,236,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2031,'base','Grenache',1123,75,'workbook projections')
ON DUPLICATE KEY UPDATE grape_kg=VALUES(grape_kg),crates_15kg=VALUES(crates_15kg),source=VALUES(source);

INSERT INTO grape_allocation_plans (estate_id,vintage_year,grape_name,total_kg,total_crates_15kg,wine_destination,blend_kg,blend_crates_15kg,varietal_kg,varietal_crates_15kg,field_instruction,source) VALUES
('00000000-0000-4000-8000-000000000001',2026,'Grecanico',1833,123,'Grecanico varietal',0,0,1833,123,'Pick and identify separately','workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'Nerello Mascalese',2560,171,'Nerello blend',2560,171,0,0,'All Nerello goes to the blend','workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'Grenache',470,32,'Nerello blend + Grenache varietal',178,12,292,20,'Pick 12 crates for the Nerello blend; 20 crates for Grenache wine','workbook projections')
ON DUPLICATE KEY UPDATE total_kg=VALUES(total_kg),total_crates_15kg=VALUES(total_crates_15kg),wine_destination=VALUES(wine_destination),blend_kg=VALUES(blend_kg),blend_crates_15kg=VALUES(blend_crates_15kg),varietal_kg=VALUES(varietal_kg),varietal_crates_15kg=VALUES(varietal_crates_15kg),field_instruction=VALUES(field_instruction),source=VALUES(source);

INSERT INTO wine_output_plans (estate_id,vintage_year,finished_wine,composition,grape_kg,wine_l,bottles_750ml,source) VALUES
('00000000-0000-4000-8000-000000000001',2026,'Grecanico','100% Grecanico',1833,1283,1711,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'Nerello blend','93.5% Nerello / 6.5% Grenache',2738,1917,2555,'workbook projections'),
('00000000-0000-4000-8000-000000000001',2026,'Grenache','Remaining Grenache',292,204,272,'workbook projections')
ON DUPLICATE KEY UPDATE composition=VALUES(composition),grape_kg=VALUES(grape_kg),wine_l=VALUES(wine_l),bottles_750ml=VALUES(bottles_750ml),source=VALUES(source);
