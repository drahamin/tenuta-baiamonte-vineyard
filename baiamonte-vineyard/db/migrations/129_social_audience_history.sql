CREATE TABLE social_account_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  platform ENUM('facebook','instagram') NOT NULL,
  external_account_id VARCHAR(190) NOT NULL,
  account_name VARCHAR(255) NULL,
  account_username VARCHAR(190) NULL,
  followers_count INT UNSIGNED NULL,
  following_count INT UNSIGNED NULL,
  media_count INT UNSIGNED NULL,
  captured_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  raw_metrics JSON NULL,
  PRIMARY KEY (id),
  KEY idx_social_snapshots_account_time (estate_id,platform,external_account_id,captured_at),
  CONSTRAINT fk_social_snapshots_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE social_audience_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  platform ENUM('facebook','instagram') NOT NULL,
  external_account_id VARCHAR(190) NOT NULL,
  event_type ENUM('net_follow','net_unfollow') NOT NULL,
  audience_change INT UNSIGNED NOT NULL,
  previous_count INT UNSIGNED NOT NULL,
  current_count INT UNSIGNED NOT NULL,
  detected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  snapshot_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_social_audience_event_snapshot (snapshot_id),
  KEY idx_social_audience_events_time (estate_id,platform,detected_at),
  CONSTRAINT fk_social_audience_events_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_social_audience_events_snapshot FOREIGN KEY (snapshot_id) REFERENCES social_account_snapshots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE social_relationship_imports (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  platform ENUM('instagram') NOT NULL DEFAULT 'instagram',
  source_filename VARCHAR(255) NULL,
  followers_count INT UNSIGNED NOT NULL DEFAULT 0,
  following_count INT UNSIGNED NOT NULL DEFAULT 0,
  imported_by VARCHAR(190) NULL,
  imported_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_social_relationship_imports_time (estate_id,platform,imported_at),
  CONSTRAINT fk_social_relationship_imports_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE social_relationship_members (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  import_id BIGINT UNSIGNED NOT NULL,
  relationship_type ENUM('follower','following') NOT NULL,
  username VARCHAR(190) NOT NULL,
  profile_url VARCHAR(500) NULL,
  relationship_timestamp BIGINT UNSIGNED NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_social_relationship_member (import_id,relationship_type,username),
  KEY idx_social_relationship_lookup (relationship_type,username),
  CONSTRAINT fk_social_relationship_member_import FOREIGN KEY (import_id) REFERENCES social_relationship_imports(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
