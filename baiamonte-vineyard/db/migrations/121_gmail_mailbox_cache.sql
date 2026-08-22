CREATE TABLE IF NOT EXISTS gmail_folder_cache (
  estate_id CHAR(36) NOT NULL,
  folder_name VARCHAR(250) NOT NULL,
  folder_label VARCHAR(250) NOT NULL,
  special_code VARCHAR(30) NULL,
  synced_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id, folder_name),
  CONSTRAINT fk_gmail_folder_cache_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gmail_message_cache (
  estate_id CHAR(36) NOT NULL,
  folder_name VARCHAR(250) NOT NULL,
  message_uid VARCHAR(40) NOT NULL,
  subject VARCHAR(998) NOT NULL,
  sender_name VARCHAR(320) NULL,
  sender_address VARCHAR(320) NULL,
  recipient_text TEXT NULL,
  sent_at VARCHAR(100) NULL,
  unread TINYINT(1) NOT NULL DEFAULT 0,
  starred TINYINT(1) NOT NULL DEFAULT 0,
  message_size BIGINT UNSIGNED NULL,
  synced_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id, folder_name, message_uid),
  KEY ix_gmail_cache_folder_time (estate_id, folder_name, synced_at),
  CONSTRAINT fk_gmail_message_cache_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
