ALTER TABLE integration_events MODIFY direction ENUM('inbound','outbound','internal') NOT NULL

;

CREATE TABLE IF NOT EXISTS ai_usage_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  feature_code VARCHAR(80) NOT NULL,
  source_record_id VARCHAR(255) NULL,
  model VARCHAR(120) NOT NULL,
  input_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
  cached_input_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
  output_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
  total_tokens BIGINT UNSIGNED NOT NULL DEFAULT 0,
  input_usd_per_million DECIMAL(12,4) NOT NULL,
  cached_input_usd_per_million DECIMAL(12,4) NOT NULL,
  output_usd_per_million DECIMAL(12,4) NOT NULL,
  estimated_cost_usd DECIMAL(14,8) NOT NULL DEFAULT 0,
  request_id VARCHAR(160) NULL,
  PRIMARY KEY (id),
  KEY idx_ai_usage_estate_time (estate_id, occurred_at),
  KEY idx_ai_usage_feature_time (estate_id, feature_code, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci

;

CREATE TABLE IF NOT EXISTS ai_cost_settings (
  estate_id CHAR(36) NOT NULL,
  monthly_budget_usd DECIMAL(12,2) NOT NULL DEFAULT 25.00,
  warning_percent DECIMAL(6,2) NOT NULL DEFAULT 80.00,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  updated_by VARCHAR(190) NULL,
  PRIMARY KEY (estate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
