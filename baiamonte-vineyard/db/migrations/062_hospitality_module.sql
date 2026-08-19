CREATE TABLE IF NOT EXISTS hospitality_packages (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(180) NOT NULL,
  experience_type ENUM('tasting','private_dinner','event') NOT NULL DEFAULT 'tasting',
  description TEXT NULL,
  duration_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 90,
  min_guests SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  max_guests SMALLINT UNSIGNED NOT NULL DEFAULT 6,
  price_basis ENUM('per_person','flat','quote') NOT NULL DEFAULT 'quote',
  price_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  deposit_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  inclusions TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY idx_hospitality_packages_estate (estate_id,active,sort_order),
  CONSTRAINT fk_hospitality_package_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hospitality_reservations (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  confirmation_code VARCHAR(24) NOT NULL,
  package_id CHAR(36) NULL,
  status ENUM('inquiry','requested','confirmed','arrived','completed','cancelled','declined','no_show') NOT NULL DEFAULT 'inquiry',
  start_at DATETIME NOT NULL,
  end_at DATETIME NOT NULL,
  guest_count SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  guest_name VARCHAR(180) NOT NULL,
  guest_email VARCHAR(320) NULL,
  guest_phone VARCHAR(80) NULL,
  preferred_language VARCHAR(12) NOT NULL DEFAULT 'en',
  dietary_restrictions TEXT NULL,
  celebration_details TEXT NULL,
  guest_preferences TEXT NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'direct',
  public_notes TEXT NULL,
  internal_notes TEXT NULL,
  quoted_total_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  deposit_received_eur DECIMAL(12,2) NOT NULL DEFAULT 0,
  assigned_manager_entity VARCHAR(255) NULL,
  created_by VARCHAR(160) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_hospitality_confirmation (estate_id,confirmation_code),
  KEY idx_hospitality_schedule (estate_id,start_at,status),
  CONSTRAINT fk_hospitality_reservation_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_hospitality_reservation_package FOREIGN KEY (package_id) REFERENCES hospitality_packages(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hospitality_communications (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  reservation_id CHAR(36) NOT NULL,
  channel ENUM('email','whatsapp','phone','note') NOT NULL,
  direction ENUM('outbound','inbound','internal') NOT NULL DEFAULT 'outbound',
  subject VARCHAR(250) NULL,
  body TEXT NOT NULL,
  delivery_status ENUM('draft','sent','failed','recorded') NOT NULL DEFAULT 'draft',
  sent_by VARCHAR(160) NULL,
  sent_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_hospitality_communications (estate_id,reservation_id,created_at),
  CONSTRAINT fk_hospitality_communication_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_hospitality_communication_reservation FOREIGN KEY (reservation_id) REFERENCES hospitality_reservations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO hospitality_packages
  (id,estate_id,name,experience_type,description,duration_minutes,min_guests,max_guests,price_basis,price_eur,deposit_eur,inclusions,active,sort_order)
SELECT UUID(),id,'Private Estate Tasting','tasting','A private, hosted tasting for one party at a time.',90,1,6,'quote',0,0,'Estate wines; hosted tasting; guest preferences recorded before arrival',1,10
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM hospitality_packages p WHERE p.estate_id=e.id AND p.name='Private Estate Tasting');

INSERT INTO hospitality_packages
  (id,estate_id,name,experience_type,description,duration_minutes,min_guests,max_guests,price_basis,price_eur,deposit_eur,inclusions,active,sort_order)
SELECT UUID(),id,'Cellar Tasting & Pairing','tasting','A longer private tasting with a simple seasonal pairing.',120,2,8,'quote',0,0,'Estate wines; cellar visit; seasonal pairing',1,20
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM hospitality_packages p WHERE p.estate_id=e.id AND p.name='Cellar Tasting & Pairing');

INSERT INTO hospitality_packages
  (id,estate_id,name,experience_type,description,duration_minutes,min_guests,max_guests,price_basis,price_eur,deposit_eur,inclusions,active,sort_order)
SELECT UUID(),id,'Private Estate Dinner','private_dinner','A private dinner package for a single party of 6–12 guests.',240,6,12,'quote',0,0,'Private dinner; estate wine pairing; dietary planning',1,30
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM hospitality_packages p WHERE p.estate_id=e.id AND p.name='Private Estate Dinner');
