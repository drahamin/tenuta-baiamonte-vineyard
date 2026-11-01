-- SOURCE DISABLED. Activation requires a reviewed backup and migration rehearsal.
ALTER TABLE mobile_intake_reports
  ADD COLUMN review_status VARCHAR(32) NOT NULL DEFAULT 'pending_review' AFTER resolved_at,
  ADD COLUMN review_revision BIGINT UNSIGNED NULL AFTER review_status,
  ADD COLUMN review_decision_uuid CHAR(36) NULL AFTER review_revision,
  ADD COLUMN review_decision_json JSON NULL AFTER review_decision_uuid,
  ADD COLUMN reviewed_by VARCHAR(80) NULL AFTER review_decision_json,
  ADD COLUMN reviewed_at DATETIME(6) NULL AFTER reviewed_by,
  ADD COLUMN review_note TEXT NULL AFTER reviewed_at,
  ADD COLUMN review_received_at DATETIME(6) NULL AFTER review_note,
  ADD UNIQUE KEY uq_mobile_intake_review_decision(review_decision_uuid),
  ADD CONSTRAINT mobile_intake_review_status_ck CHECK (review_status IN ('pending_review','approved','rejected','correction_required'));
