-- SOURCE DISABLED. Test/rehearsal schema only.
ALTER TABLE mobile_intake_reports ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending_review';
ALTER TABLE mobile_intake_reports ADD COLUMN review_revision INTEGER NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN review_decision_uuid TEXT NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN review_decision_json TEXT NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN reviewed_by TEXT NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN reviewed_at TEXT NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN review_note TEXT NULL;
ALTER TABLE mobile_intake_reports ADD COLUMN review_received_at TEXT NULL;
CREATE UNIQUE INDEX uq_mobile_intake_review_decision ON mobile_intake_reports(review_decision_uuid);
