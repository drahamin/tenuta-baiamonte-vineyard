ALTER TABLE scouting_observations
  MODIFY COLUMN block_id CHAR(36) NULL,
  ADD COLUMN IF NOT EXISTS variety_id CHAR(36) NULL AFTER block_id,
  ADD COLUMN IF NOT EXISTS damage_scope ENUM('zone','block','variety','estate') NOT NULL DEFAULT 'block' AFTER damage_type,
  ADD COLUMN IF NOT EXISTS reported_zone_area_ha DECIMAL(10,4) NULL AFTER damage_scope,
  ADD COLUMN IF NOT EXISTS representative_survey TINYINT(1) NOT NULL DEFAULT 0 AFTER reported_zone_area_ha,
  ADD COLUMN IF NOT EXISTS ai_zone_damage_pct DECIMAL(6,2) NULL AFTER estimated_yield_loss_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_damage_low_pct DECIMAL(6,2) NULL AFTER ai_zone_damage_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_damage_high_pct DECIMAL(6,2) NULL AFTER ai_zone_damage_low_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_yield_reduction_pct DECIMAL(6,2) NULL AFTER ai_zone_damage_high_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_yield_reduction_low_pct DECIMAL(6,2) NULL AFTER ai_zone_yield_reduction_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_yield_reduction_high_pct DECIMAL(6,2) NULL AFTER ai_zone_yield_reduction_low_pct,
  ADD COLUMN IF NOT EXISTS ai_zone_analysis_json JSON NULL AFTER ai_zone_yield_reduction_high_pct,
  ADD INDEX IF NOT EXISTS ix_scouting_damage_scope (estate_id,season_id,damage_scope,variety_id,observed_at);

UPDATE scouting_observations
SET damage_scope='block',representative_survey=0
WHERE damage_scope IS NULL;

UPDATE vineyard_damage_assessments
SET scope_type='estate',block_id=NULL,variety_id=NULL,affected_area_pct=NULL,estimated_yield_loss_pct=NULL,
    notes=CONCAT(COALESCE(notes,''),CASE WHEN COALESCE(notes,'')='' THEN '' ELSE '\n' END,'Authoritative scope confirmation: the 2026 hailstorm event chain is estate-wide.')
WHERE event_key='hail-2026-06-27';
