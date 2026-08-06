CREATE UNIQUE INDEX IF NOT EXISTS uq_people_estate_name ON people (estate_id, name);

ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS agronomist_approved TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS label_legal_confirmed TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS phi_checked TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS rei_checked TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS weather_checked TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE spray_applications ADD COLUMN IF NOT EXISTS ppe_confirmed TINYINT(1) NOT NULL DEFAULT 0;
