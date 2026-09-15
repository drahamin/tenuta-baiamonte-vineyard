ALTER TABLE fermentation_observations
  ADD COLUMN IF NOT EXISTS babo DECIMAL(7,3) NULL AFTER brix;

ALTER TABLE cellar_control_profiles
  ADD COLUMN IF NOT EXISTS manual_babo DECIMAL(7,3) NULL AFTER manual_brix;
