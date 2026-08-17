ALTER TABLE cellar_control_profiles
  ADD COLUMN IF NOT EXISTS wine_color VARCHAR(16) NULL AFTER manual_contents;

ALTER TABLE wine_lot_legal_profiles
  ADD COLUMN IF NOT EXISTS wine_color VARCHAR(16) NULL AFTER wine_type;
