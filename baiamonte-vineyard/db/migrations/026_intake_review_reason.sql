ALTER TABLE intake_items
  ADD COLUMN IF NOT EXISTS review_reason TEXT NULL AFTER review_status;
