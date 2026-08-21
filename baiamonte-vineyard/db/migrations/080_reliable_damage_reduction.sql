ALTER TABLE vineyard_damage_assessments
  ADD COLUMN scope_type ENUM('estate','variety','block_variety') NOT NULL DEFAULT 'estate' AFTER trend,
  ADD COLUMN block_id CHAR(36) NULL AFTER scope_type,
  ADD COLUMN variety_id CHAR(36) NULL AFTER block_id,
  ADD COLUMN affected_area_pct DECIMAL(6,2) NULL AFTER estate_yield_loss_pct,
  ADD COLUMN estimated_yield_loss_pct DECIMAL(6,2) NULL AFTER affected_area_pct,
  ADD KEY ix_damage_assessment_scope (estate_id,season_id,scope_type,block_id,variety_id),
  ADD CONSTRAINT fk_damage_assessment_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_damage_assessment_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL;

UPDATE vineyard_damage_assessments
SET scope_type='estate',block_id=NULL,variety_id=NULL,affected_area_pct=NULL,estimated_yield_loss_pct=NULL
WHERE estate_yield_loss_pct IS NOT NULL OR scope_type IS NULL;
