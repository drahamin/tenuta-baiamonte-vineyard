-- Fatture in Cloud can return signed authoritative-document URLs longer than
-- the original 500-character field. Keep the URL intact without allowing one
-- long source reference to roll back the complete finance synchronization.
ALTER TABLE financial_documents
  MODIFY COLUMN source_document TEXT NULL;
