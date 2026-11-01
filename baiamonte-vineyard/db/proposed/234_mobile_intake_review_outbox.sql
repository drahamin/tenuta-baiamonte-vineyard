-- SOURCE DISABLED. Do not move into db/migrations until the activation bundle is approved.
CREATE TABLE IF NOT EXISTS mobile_intake_review_outbox (
  decision_uuid CHAR(36) NOT NULL PRIMARY KEY,
  report_uuid CHAR(36) NOT NULL,
  estate_id CHAR(36) NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  status ENUM('pending','delivered') NOT NULL DEFAULT 'pending',
  attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  next_attempt_at DATETIME(6) NOT NULL,
  delivered_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_mobile_intake_review_report(report_uuid),
  KEY ix_mobile_intake_review_delivery(estate_id,status,next_attempt_at),
  CONSTRAINT fk_mobile_intake_review_report FOREIGN KEY (report_uuid) REFERENCES mobile_intake_source_drafts(report_uuid) ON DELETE RESTRICT,
  CONSTRAINT fk_mobile_intake_review_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
