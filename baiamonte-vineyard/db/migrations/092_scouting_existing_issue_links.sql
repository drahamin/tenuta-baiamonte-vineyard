ALTER TABLE scouting_observations
  ADD COLUMN linked_issue_id VARCHAR(120) NULL AFTER damage_event_key,
  ADD KEY ix_scouting_linked_issue (estate_id,linked_issue_id,observed_at);
