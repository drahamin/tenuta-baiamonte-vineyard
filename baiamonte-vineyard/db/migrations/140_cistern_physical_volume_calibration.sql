ALTER TABLE water_deliveries
  ADD COLUMN delivery_volume_l DECIMAL(12,2) NOT NULL DEFAULT 5000.00 AFTER declared_amount_eur,
  ADD COLUMN volume_source VARCHAR(80) NOT NULL DEFAULT 'nunzio_standard_delivery' AFTER delivery_volume_l,
  ADD COLUMN calibration_eligible TINYINT(1) NOT NULL DEFAULT 0 AFTER level_increase_pct,
  ADD COLUMN implied_cistern_capacity_l DECIMAL(14,2) NULL AFTER calibration_eligible,
  ADD KEY ix_water_delivery_volume_calibration (estate_id,calibration_eligible,completed_at);

UPDATE water_deliveries
SET delivery_volume_l=5000.00,
    volume_source='nunzio_standard_delivery'
WHERE delivery_volume_l IS NULL OR delivery_volume_l=5000.00;
