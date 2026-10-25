ALTER TABLE vintage_designation_plan_source_lots
  ADD COLUMN IF NOT EXISTS source_type ENUM('estate','purchased','unknown') NOT NULL DEFAULT 'unknown'
  AFTER component_role;
