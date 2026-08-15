ALTER TABLE intake_items
  MODIFY COLUMN review_status ENUM('new','processing','ready_for_review','approved','rejected','failed','archived') NOT NULL DEFAULT 'new',
  ADD COLUMN archived_at DATETIME(6) NULL AFTER reviewed_at;
