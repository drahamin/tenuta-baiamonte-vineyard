CREATE TABLE IF NOT EXISTS alert_preferences (
  estate_id CHAR(36) NOT NULL,
  alert_type VARCHAR(80) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  min_severity ENUM('info','warning','critical') NOT NULL DEFAULT 'warning',
  notify_home_assistant TINYINT(1) NOT NULL DEFAULT 1,
  notify_email TINYINT(1) NOT NULL DEFAULT 0,
  notify_whatsapp TINYINT(1) NOT NULL DEFAULT 0,
  email_recipients TEXT NULL,
  whatsapp_recipients TEXT NULL,
  updated_by VARCHAR(180) NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (estate_id,alert_type),
  CONSTRAINT fk_alert_pref_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
