-- Agronomist/enologist process captured from the 2026-09-02 cellar meeting.
-- Proposed rates remain reviewable; nothing in this schema authorizes an addition.
CREATE TABLE IF NOT EXISTS enology_process_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  wine_color ENUM('red','white','rose') NOT NULL,
  target_style VARCHAR(180) NULL,
  target_press_at DATETIME(6) NULL,
  yan_mg_l DECIMAL(10,3) NULL,
  yan_sampled_at DATETIME(6) NULL,
  yan_target_mg_l DECIMAL(10,3) NOT NULL DEFAULT 150,
  approved_yeast VARCHAR(180) NULL,
  process_status ENUM('draft','approved','active','complete','held') NOT NULL DEFAULT 'draft',
  approved_by VARCHAR(190) NULL,
  approved_at DATETIME(6) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_process_lot (estate_id,wine_lot_id),
  CONSTRAINT fk_enology_process_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_process_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enology_additive_catalog (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(180) NOT NULL,
  additive_type ENUM('yeast','enzyme','nutrient','tannin','other') NOT NULL,
  wine_color ENUM('red','white','rose','any') NOT NULL DEFAULT 'any',
  process_stage VARCHAR(80) NOT NULL,
  proposed_rate DECIMAL(12,4) NULL,
  proposed_rate_unit VARCHAR(40) NULL,
  timing_rule VARCHAR(255) NULL,
  purpose TEXT NULL,
  source_reference VARCHAR(255) NULL,
  approval_required TINYINT(1) NOT NULL DEFAULT 1,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_additive_name (estate_id,name,additive_type),
  CONSTRAINT fk_enology_additive_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enology_addition_events (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  additive_id CHAR(36) NULL,
  additive_name VARCHAR(180) NOT NULL,
  additive_type ENUM('yeast','enzyme','nutrient','tannin','other') NOT NULL,
  event_status ENUM('planned','approved','applied','cancelled') NOT NULL DEFAULT 'planned',
  scheduled_at DATETIME(6) NULL,
  applied_at DATETIME(6) NULL,
  quantity DECIMAL(12,4) NULL,
  unit VARCHAR(40) NULL,
  product_lot VARCHAR(120) NULL,
  reason_text TEXT NULL,
  approved_by VARCHAR(190) NULL,
  approved_at DATETIME(6) NULL,
  recorded_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_enology_additions_lot (estate_id,wine_lot_id,scheduled_at,applied_at),
  CONSTRAINT fk_enology_addition_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_addition_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_addition_catalog FOREIGN KEY (additive_id) REFERENCES enology_additive_catalog(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enology_test_requests (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NULL,
  variety_id CHAR(36) NULL,
  block_id CHAR(36) NULL,
  requested_at DATETIME(6) NOT NULL,
  due_at DATETIME(6) NOT NULL,
  process_stage VARCHAR(80) NOT NULL,
  sample_type ENUM('grape','must','wine') NOT NULL,
  sample_scope VARCHAR(255) NOT NULL,
  analytes_json JSON NOT NULL,
  calculation_rules_json JSON NULL,
  status ENUM('scheduled','sampled','result_received','reviewed','cancelled') NOT NULL DEFAULT 'scheduled',
  result_sample_id CHAR(36) NULL,
  requested_by VARCHAR(190) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_enology_test_due (estate_id,status,due_at),
  CONSTRAINT fk_enology_test_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_test_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_test_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL,
  CONSTRAINT fk_enology_test_variety FOREIGN KEY (variety_id) REFERENCES grape_varieties(id) ON DELETE SET NULL,
  CONSTRAINT fk_enology_test_block FOREIGN KEY (block_id) REFERENCES vineyard_blocks(id) ON DELETE SET NULL,
  CONSTRAINT fk_enology_test_sample FOREIGN KEY (result_sample_id) REFERENCES lab_samples(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,proposed_rate,proposed_rate_unit,timing_rule,purpose,source_reference)
SELECT UUID(),id,'Zymaflor Alpha','yeast','white','inoculation',30,'g/hL','After must analysis and enologist approval','Proposed white-wine yeast for a citrus-oriented aromatic profile','PLAUD meeting 2026-09-02' FROM estates;
INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,proposed_rate,proposed_rate_unit,timing_rule,purpose,source_reference)
SELECT UUID(),id,'White pressing enzyme','enzyme','white','pressing',NULL,NULL,'First step on the press; exact product and rate remain unconfirmed','Pressing and aroma extraction','PLAUD meeting 2026-09-02' FROM estates;
INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,proposed_rate,proposed_rate_unit,timing_rule,purpose,source_reference)
SELECT UUID(),id,'Red pre-press enzyme','enzyme','red','fermentation',1,'g/hL','Final two days of fermentation before pressing','Extraction before pressing','PLAUD meeting 2026-09-02' FROM estates;
INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,timing_rule,purpose,source_reference)
SELECT UUID(),id,'Yeast nutrient','nutrient','any','pre-fermentation','Only after measured YAN; product and conversion rule remain unconfirmed','Correct a verified yeast-assimilable nitrogen deficit','PLAUD meeting 2026-09-02' FROM estates;
INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,timing_rule,purpose,source_reference)
SELECT UUID(),id,'Red color-stabilization tannin','tannin','red','crushing','At crushing; exact product and dose require enologist approval','Bind polyphenols and support color stability','PLAUD meeting 2026-09-02' FROM estates;
INSERT IGNORE INTO enology_additive_catalog
  (id,estate_id,name,additive_type,wine_color,process_stage,timing_rule,purpose,source_reference)
SELECT UUID(),id,'Post-fermentation aging tannin','tannin','red','post-press','Optional after pressing/fermentation; exact product and dose require enologist approval','Potential stabilization and aging support','PLAUD meeting 2026-09-02' FROM estates;

-- Tomorrow's exact request. Each physical bag still needs its own variety/block
-- identification; the request is not treated as a result until a lab sample is linked.
INSERT INTO enology_test_requests
  (id,estate_id,season_id,requested_at,due_at,process_stage,sample_type,sample_scope,analytes_json,calculation_rules_json,status,requested_by,notes)
SELECT UUID(),s.estate_id,s.id,'2026-09-02 17:00:00','2026-09-03 07:00:00','pre-harvest','grape',
  'Separate representative grape sample for each color/variety/block bag; do not combine red and white results',
  JSON_ARRAY('ph','total_acidity','babo','potassium','potential_alcohol'),
  JSON_OBJECT('potential_alcohol','Calculate from Babo using the estate historical paired-result model; disclose factor, evidence count and confidence'),
  'scheduled','Agronomist meeting 2026-09-02',
  'Sample consistently from the top through the vineyard at 07:00–07:30. Do not select only attractive bunches. Potential alcohol is calculated, not separately measured.'
FROM seasons s
WHERE s.vintage_year=2026
  AND NOT EXISTS (SELECT 1 FROM enology_test_requests r WHERE r.season_id=s.id AND r.due_at='2026-09-03 07:00:00');

INSERT INTO tasks (id,estate_id,season_id,title,category,status,priority,due_date,notes,source)
SELECT UUID(),s.estate_id,s.id,'Collect agronomist-requested grape samples','laboratory','planned','urgent','2026-09-03',
  '07:00–07:30. Keep each color/variety/block bag identified. Request pH, total acidity, Babo and potassium; calculate potential alcohol from Babo with the disclosed estate model.',
  'PLAUD meeting 2026-09-02'
FROM seasons s
WHERE s.vintage_year=2026
  AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.season_id=s.id AND t.title='Collect agronomist-requested grape samples' AND t.due_date='2026-09-03');
