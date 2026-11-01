-- PROPOSAL ONLY. This directory is not read by the migration runner.
CREATE TABLE mobile_domain_action_receipts (
  action_uuid CHAR(36) NOT NULL PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  workflow ENUM('timeclock','cellar') NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  status ENUM('processing','accepted','rejected','conflict') NOT NULL,
  result_json JSON NOT NULL,
  resolved_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_mobile_domain_receipt_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE mobile_timeclock_events (
  event_uuid CHAR(36) NOT NULL PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  shift_uuid CHAR(36) NOT NULL,
  person_id CHAR(36) NOT NULL,
  actor_username VARCHAR(80) NOT NULL,
  event_type ENUM('clock_in','break_start','break_end','clock_out') NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  shift_revision BIGINT UNSIGNED NOT NULL,
  payload_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_mobile_timeclock_shift_revision(shift_uuid,shift_revision),
  KEY ix_mobile_timeclock_shift(estate_id,shift_uuid,occurred_at),
  CONSTRAINT fk_mobile_timeclock_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE RESTRICT,
  CONSTRAINT fk_mobile_timeclock_person FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE RESTRICT,
  CONSTRAINT fk_mobile_timeclock_labor FOREIGN KEY (shift_uuid) REFERENCES labor_entries(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
