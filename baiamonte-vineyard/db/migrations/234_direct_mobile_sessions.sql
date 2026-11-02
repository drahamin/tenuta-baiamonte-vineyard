CREATE TABLE IF NOT EXISTS mobile_site_sessions (
  token_hash CHAR(64) NOT NULL PRIMARY KEY,
  ha_user_id VARCHAR(128) NOT NULL,
  identity_version BIGINT UNSIGNED NOT NULL,
  audience VARCHAR(191) NOT NULL,
  capabilities_json TEXT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  revoked_at DATETIME(6) NULL,
  INDEX mobile_site_sessions_user_expiry_idx (ha_user_id,expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mobile_site_exchange_nonces (
  nonce_hash CHAR(64) NOT NULL PRIMARY KEY,
  issued_at BIGINT UNSIGNED NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX mobile_site_exchange_nonces_expiry_idx (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
