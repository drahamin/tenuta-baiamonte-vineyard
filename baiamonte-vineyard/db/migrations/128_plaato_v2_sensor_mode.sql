ALTER TABLE cellar_control_profiles
  MODIFY reading_mode ENUM('manual','sensor','auto') NOT NULL DEFAULT 'manual';
