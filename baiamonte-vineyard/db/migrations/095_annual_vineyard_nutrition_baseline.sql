-- This is an annual evidence-and-review baseline, never an automatic
-- fertilizer prescription. Nutrition planning is separated from disease
-- control, but an approved application continues through Treatments for
-- calculation, inventory, weather, approval and completion.
CREATE TABLE IF NOT EXISTS crop_nutrition_baselines (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  crop_scope ENUM('vineyard','olives') NOT NULL,
  phase_order SMALLINT UNSIGNED NOT NULL,
  stage_code VARCHAR(60) NOT NULL,
  stage_label VARCHAR(120) NOT NULL,
  objective TEXT NOT NULL,
  evidence_gate TEXT NOT NULL,
  baseline_action ENUM('monitor','sample_and_review','no_routine_application') NOT NULL DEFAULT 'monitor',
  product_review_json JSON NULL,
  agronomist_notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_crop_nutrition_stage (estate_id,season_id,crop_scope,stage_code),
  KEY ix_crop_nutrition_order (estate_id,season_id,crop_scope,phase_order),
  CONSTRAINT fk_crop_nutrition_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_crop_nutrition_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crop_nutrition_baselines
  (id,estate_id,season_id,crop_scope,phase_order,stage_code,stage_label,objective,evidence_gate,baseline_action,product_review_json,agronomist_notes)
SELECT UUID(),e.id,s.id,x.crop_scope,x.phase_order,x.stage_code,x.stage_label,x.objective,x.evidence_gate,x.baseline_action,x.product_review_json,
  '2026 annual baseline. Products are review candidates only; evidence, current crop directions, stock, compatibility, weather and Agronomist approval remain mandatory.'
FROM estates e JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN (
  SELECT 'vineyard' crop_scope,10 phase_order,'dormant' stage_code,'Dormant / preseason' stage_label,
    'Establish soil fertility, organic matter, pH, salinity and reserve status before growth begins.' objective,
    'Current soil analysis and prior-year tissue/yield review. Do not infer a deficiency from calendar timing.' evidence_gate,
    'sample_and_review' baseline_action,JSON_ARRAY('TERRAPLUS SOLUB NPK 8-7-6') product_review_json UNION ALL
  SELECT 'vineyard',20,'budbreak','Budbreak','Support balanced early shoot development without forcing excess vigor.',
    'Recorded budbreak plus soil/tissue evidence, shoot vigor and water status. Copper/manganese nutrition requires a recognized deficiency.',
    'sample_and_review',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM','FERTICUS 18 M') UNION ALL
  SELECT 'vineyard',30,'shoot_growth','Shoot growth','Monitor canopy growth, chlorosis, micronutrient symptoms and water stress.',
    'Block scouting plus leaf/tissue analysis when symptoms, weak growth or uneven vigor are present.',
    'sample_and_review',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM','FERTICUS 18 M') UNION ALL
  SELECT 'vineyard',40,'flowering','Flowering','Protect flowering and fruit set from avoidable nutritional or abiotic stress without routine nitrogen loading.',
    'Recorded flowering, flower/fruit-set observations, vigor and tissue evidence. Avoid speculative nutrition from weather alone.',
    'monitor',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM') UNION ALL
  SELECT 'vineyard',50,'fruit_set','Fruit set','Review fruit load, canopy balance, berry development and stress recovery.',
    'Fruit-set percentage, crop-load estimate, leaf/tissue analysis and water-stress observations.',
    'sample_and_review',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM','GEL DI SILICE','RESOLVE') UNION ALL
  SELECT 'vineyard',60,'bunch_closure','Bunch closure','Maintain balanced canopy and berry development while avoiding unnecessary late vegetative stimulation.',
    'Block scouting, crop load, tissue evidence and documented biotic/abiotic stress. Support products are not disease control.',
    'monitor',JSON_ARRAY('GEL DI SILICE','RESOLVE','FRONTIERE') UNION ALL
  SELECT 'vineyard',70,'veraison','Veraison','Prioritize ripening balance, berry integrity and water-stress management; avoid routine late nitrogen.',
    'Recorded veraison, berry chemistry trend, canopy status and documented stress. Confirm harvest interval before any application.',
    'monitor',JSON_ARRAY('GEL DI SILICE','RESOLVE') UNION ALL
  SELECT 'vineyard',80,'ripening','Ripening / preharvest','Protect fruit quality and maturity trajectory without unsupported nutrition or residue risk.',
    'Laboratory maturity, tasting, berry condition, forecast harvest date and every applicable PHI. No routine application.',
    'no_routine_application',JSON_ARRAY() UNION ALL
  SELECT 'vineyard',90,'post_harvest','Postharvest','Assess reserve replenishment only after yield, canopy condition and soil evidence are reviewed.',
    'Final yield, postharvest canopy condition, soil/tissue evidence and irrigation/rainfall outlook.',
    'sample_and_review',JSON_ARRAY('TERRAPLUS SOLUB NPK 8-7-6') UNION ALL
  SELECT 'olives',10,'olive_dormant','Dormant / preseason','Review soil condition, organic matter, pH, salinity, prior yield and tree reserve status.',
    'Current soil analysis, prior harvest yield/oil recovery and tree-vigor review. Calendar timing alone is not a deficiency.',
    'sample_and_review',JSON_ARRAY('TERRAPLUS SOLUB NPK 8-7-6') UNION ALL
  SELECT 'olives',20,'olive_budbreak','Vegetative restart','Support balanced new growth only where evidence establishes a need.',
    'Tree/block scouting, current soil or leaf evidence and water status.',
    'sample_and_review',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM','FERTICUS 18 M') UNION ALL
  SELECT 'olives',30,'olive_flowering','Flowering','Protect flowering and potential fruit set without speculative nutrient loading.',
    'Flowering observations, prior alternate-bearing pattern, vigor, water status and tissue evidence.',
    'monitor',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM') UNION ALL
  SELECT 'olives',40,'olive_fruit_set','Fruit set / early growth','Review crop load, fruit set, shoot balance and recovery from documented stress.',
    'Fruit-set and crop-load observations, leaf evidence and water-stress report.',
    'sample_and_review',JSON_ARRAY('FRONTIERE','IMPULSIVE PREMIUM','GEL DI SILICE','RESOLVE') UNION ALL
  SELECT 'olives',50,'olive_pit_hardening','Pit hardening / fruit growth','Maintain water and nutritional balance without routine unsupported foliar additions.',
    'Fruit-development observations, irrigation/rainfall, canopy condition and tissue evidence.',
    'monitor',JSON_ARRAY('GEL DI SILICE','RESOLVE') UNION ALL
  SELECT 'olives',60,'olive_ripening','Oil accumulation / ripening','Protect fruit quality and oil accumulation while avoiding unnecessary late nitrogen.',
    'Fruit maturity, pest/disease status, water status and forecast harvest date. No routine product application.',
    'no_routine_application',JSON_ARRAY() UNION ALL
  SELECT 'olives',70,'olive_post_harvest','Postharvest','Review reserve replenishment after actual yield, oil recovery and canopy condition are known.',
    'Final olive kg, oil liters/recovery, soil or tissue evidence and rainfall outlook.',
    'sample_and_review',JSON_ARRAY('TERRAPLUS SOLUB NPK 8-7-6')
) x
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE
  phase_order=VALUES(phase_order),stage_label=VALUES(stage_label),objective=VALUES(objective),
  evidence_gate=VALUES(evidence_gate),baseline_action=VALUES(baseline_action),product_review_json=VALUES(product_review_json),active=1;

-- Application totals are authoritative, while operator, exact scope and safety
-- confirmations remain open. Do not mark the entire application verified.
UPDATE spray_applications
SET operator_name=NULL,
    evidence_status='owner-confirmed application, water volume, products and per-100-L rates; scope, operator and safety details pending'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND crop_scope='vineyard' AND LOWER(TRIM(purpose))='treatment 5'
  AND status='completed' AND DATE(application_date)='2026-06-27' AND water_volume_l=400;
