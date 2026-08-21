ALTER TABLE scouting_observations
  ADD COLUMN damage_event_key VARCHAR(120) NULL AFTER damage_type,
  ADD COLUMN damage_proposal_status ENUM('not_calculated','calculated','promoted','dismissed') NOT NULL DEFAULT 'not_calculated' AFTER yield_impact_review_status,
  ADD COLUMN proposed_estate_loss_pct DECIMAL(6,2) NULL AFTER damage_proposal_status,
  ADD COLUMN damage_proposal_json JSON NULL AFTER proposed_estate_loss_pct,
  ADD KEY ix_scouting_damage_event (estate_id,season_id,damage_event_key,observed_at),
  ADD KEY ix_scouting_damage_proposal (estate_id,season_id,damage_proposal_status,observed_at);

ALTER TABLE vineyard_damage_assessments
  ADD COLUMN source_scouting_id CHAR(36) NULL AFTER source_reference,
  ADD COLUMN calculation_json JSON NULL AFTER evidence_json,
  ADD UNIQUE KEY uq_damage_assessment_source_variety (source_scouting_id,variety_id),
  ADD CONSTRAINT fk_damage_assessment_scouting FOREIGN KEY (source_scouting_id) REFERENCES scouting_observations(id) ON DELETE SET NULL;
