CREATE TABLE IF NOT EXISTS mobile_intake_source_drafts (
  report_uuid CHAR(36) NOT NULL PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  actor_username VARCHAR(80) NOT NULL,
  actor_role VARCHAR(40) NOT NULL,
  entry_kind ENUM('field_observation','damage_report','work_report','cellar_note','agronomy_note','enology_reading') NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  received_at DATETIME(6) NOT NULL,
  source_timezone VARCHAR(64) NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  correction_of_report_uuid CHAR(36) NULL,
  ingest_status ENUM('validated','conflict','rejected') NOT NULL DEFAULT 'validated',
  validation_reason VARCHAR(160) NULL,
  ingest_result_json JSON NOT NULL,
  status ENUM('pending_review','approved','rejected','correction_required','superseded') NOT NULL DEFAULT 'pending_review',
  revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
  reviewed_by VARCHAR(160) NULL,
  reviewed_at DATETIME(6) NULL,
  review_note TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_mobile_intake_source_review (estate_id,status,entry_kind,received_at),
  CONSTRAINT fk_mobile_intake_source_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE RESTRICT,
  CONSTRAINT fk_mobile_intake_source_correction FOREIGN KEY (correction_of_report_uuid) REFERENCES mobile_intake_source_drafts(report_uuid) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Upgrade a table created by an earlier staged revision. Backfilled outcomes
-- deliberately do not claim durable evidence; the website must retain its
-- copy until a newly verified receipt can be recorded.
ALTER TABLE mobile_intake_source_drafts
  ADD COLUMN IF NOT EXISTS ingest_result_json JSON NULL AFTER validation_reason;
UPDATE mobile_intake_source_drafts
SET ingest_result_json=JSON_OBJECT(
  'authoritative_record_ids',JSON_ARRAY(report_uuid),
  'actual_revisions',JSON_OBJECT(),
  'reason',COALESCE(validation_reason,IF(ingest_status='validated','pending_review',ingest_status)),
  'evidence_durable',FALSE
)
WHERE ingest_result_json IS NULL;
ALTER TABLE mobile_intake_source_drafts
  MODIFY COLUMN ingest_result_json JSON NOT NULL;
