CREATE TABLE IF NOT EXISTS harvest_lot_parcels (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  harvest_lot_id CHAR(36) NOT NULL,
  parcel_id CHAR(36) NOT NULL,
  contribution_kg DECIMAL(12,3) NULL,
  crate_count INT UNSIGNED NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_harvest_lot_parcel (harvest_lot_id, parcel_id),
  KEY ix_harvest_parcel_estate (estate_id, parcel_id),
  CONSTRAINT fk_harvest_parcel_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_harvest_parcel_lot FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(id) ON DELETE CASCADE,
  CONSTRAINT fk_harvest_parcel_parcel FOREIGN KEY (parcel_id) REFERENCES cadastral_parcels(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
