CREATE TABLE IF NOT EXISTS wine_lot_legal_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  wine_type VARCHAR(80) NULL,
  vintage_year SMALLINT NULL,
  origin_country VARCHAR(120) NOT NULL DEFAULT 'Italia',
  denomination_class VARCHAR(80) NULL,
  denomination VARCHAR(190) NULL,
  content_description VARCHAR(255) NULL,
  processing_phase VARCHAR(190) NULL,
  racking_history TEXT NULL,
  legal_notes TEXT NULL,
  confirmed_by VARCHAR(190) NULL,
  confirmed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_wine_lot_legal_profile (wine_lot_id),
  KEY ix_wine_lot_legal_estate (estate_id, updated_at),
  CONSTRAINT fk_wine_lot_legal_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_wine_lot_legal_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cellar_tank_labels (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  container_id CHAR(36) NOT NULL,
  public_token CHAR(36) NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  retired_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_cellar_tank_label_container (container_id),
  UNIQUE KEY uq_cellar_tank_label_token (public_token),
  KEY ix_cellar_tank_label_estate (estate_id, active),
  CONSTRAINT fk_cellar_tank_label_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_cellar_tank_label_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cellar_label_kiosks (
  id CHAR(36) NOT NULL,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(160) NOT NULL,
  public_token CHAR(36) NOT NULL,
  container_id CHAR(36) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  notes TEXT NULL,
  last_seen_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_cellar_label_kiosk_token (public_token),
  KEY idx_cellar_label_kiosks_estate_active (estate_id, active),
  KEY idx_cellar_label_kiosks_container (container_id),
  CONSTRAINT fk_cellar_label_kiosk_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellar_label_kiosk_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO cellar_tank_labels (id, estate_id, container_id, public_token, active)
SELECT UUID(), c.estate_id, c.id, UUID(), c.active
FROM cellar_containers c;
