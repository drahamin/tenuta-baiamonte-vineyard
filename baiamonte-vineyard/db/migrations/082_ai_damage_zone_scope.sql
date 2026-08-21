CREATE TABLE IF NOT EXISTS scouting_damage_scopes (
  observation_id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  variety_id CHAR(36) NULL,
  damage_scope ENUM('zone','block','variety','estate') NOT NULL DEFAULT 'block',
  reported_zone_area_ha DECIMAL(10,4) NULL,
  representative_survey TINYINT(1) NOT NULL DEFAULT 0,
  ai_zone_damage_pct DECIMAL(6,2) NULL,
  ai_zone_damage_low_pct DECIMAL(6,2) NULL,
  ai_zone_damage_high_pct DECIMAL(6,2) NULL,
  ai_zone_yield_reduction_pct DECIMAL(6,2) NULL,
  ai_zone_yield_reduction_low_pct DECIMAL(6,2) NULL,
  ai_zone_yield_reduction_high_pct DECIMAL(6,2) NULL,
  ai_zone_analysis_json JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_scouting_damage_scope (estate_id,damage_scope,variety_id,observation_id),
  CONSTRAINT fk_scout_scope_observation FOREIGN KEY (observation_id) REFERENCES scouting_observations(id) ON DELETE CASCADE,
  CONSTRAINT fk_scout_scope_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_scout_scope_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO scouting_damage_scopes (observation_id,estate_id,damage_scope,representative_survey)
SELECT id,estate_id,'block',0 FROM scouting_observations
ON DUPLICATE KEY UPDATE observation_id=VALUES(observation_id);

UPDATE vineyard_damage_assessments
SET scope_type='estate',block_id=NULL,variety_id=NULL,affected_area_pct=NULL,estimated_yield_loss_pct=NULL,
    notes=CONCAT(COALESCE(notes,''),CASE WHEN COALESCE(notes,'')='' THEN '' ELSE '\n' END,'Authoritative scope confirmation: the 2026 hailstorm event chain is estate-wide.')
WHERE event_key='hail-2026-06-27';
