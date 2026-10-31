-- Separate ledger entry for installations that already recorded migration 232
-- before ingest_result_json was added to its CREATE TABLE definition.
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
