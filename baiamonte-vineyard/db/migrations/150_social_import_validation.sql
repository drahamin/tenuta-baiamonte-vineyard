ALTER TABLE social_relationship_imports
  ADD COLUMN validation_status ENUM('accepted','quarantined') NOT NULL DEFAULT 'accepted' AFTER imported_by,
  ADD COLUMN validation_note VARCHAR(500) NULL AFTER validation_status;

UPDATE social_relationship_imports imports
JOIN (
  SELECT snapshots.estate_id,snapshots.followers_count,snapshots.captured_at
  FROM social_account_snapshots snapshots
  LEFT JOIN social_account_snapshots newer
    ON newer.estate_id=snapshots.estate_id
   AND newer.platform='instagram'
   AND newer.id>snapshots.id
  WHERE snapshots.platform='instagram' AND newer.id IS NULL
) current_account ON current_account.estate_id=imports.estate_id
SET imports.validation_status='quarantined',
    imports.validation_note='Partial Meta export: follower records are materially below the verified Instagram account total.'
WHERE imports.platform='instagram'
  AND imports.imported_at>=DATE_SUB(current_account.captured_at,INTERVAL 30 DAY)
  AND imports.followers_count < (current_account.followers_count * 0.80);
