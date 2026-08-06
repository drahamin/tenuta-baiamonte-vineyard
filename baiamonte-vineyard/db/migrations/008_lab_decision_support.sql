CREATE TABLE IF NOT EXISTS lab_reference_ranges (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  analyte_code VARCHAR(80) NOT NULL,
  analyte_name VARCHAR(160) NOT NULL,
  sample_type ENUM('grape','must','wine','soil','water','other') NULL,
  stage VARCHAR(100) NULL,
  unit VARCHAR(50) NULL,
  target_min DECIMAL(16,6) NULL,
  target_max DECIMAL(16,6) NULL,
  review_below DECIMAL(16,6) NULL,
  review_above DECIMAL(16,6) NULL,
  effective_from DATE NULL,
  effective_to DATE NULL,
  source_reference VARCHAR(700) NULL,
  approved_by VARCHAR(180) NULL,
  approval_date DATE NULL,
  notes TEXT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_lab_reference_range (estate_id,analyte_code,sample_type,stage,effective_from),
  CONSTRAINT fk_lab_reference_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lab_reviews (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  sample_id CHAR(36) NOT NULL,
  review_status ENUM('unreviewed','reviewing','decision_needed','monitoring','closed') NOT NULL DEFAULT 'unreviewed',
  interpretation MEDIUMTEXT NULL,
  decision_action MEDIUMTEXT NULL,
  decision_type ENUM('observe','repeat_test','adjustment','hold','release','investigate','other') NULL,
  owner_text VARCHAR(180) NULL,
  next_check_at DATETIME(6) NULL,
  enologist_approval_required TINYINT(1) NOT NULL DEFAULT 1,
  approved_by VARCHAR(180) NULL,
  approved_at DATETIME(6) NULL,
  evidence_reference_id CHAR(36) NULL,
  notes MEDIUMTEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_lab_review_sample (sample_id),
  CONSTRAINT fk_lab_review_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_review_sample FOREIGN KEY (sample_id) REFERENCES lab_samples(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_review_evidence FOREIGN KEY (evidence_reference_id) REFERENCES evidence_references(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lab_decision_notes (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  sample_id CHAR(36) NULL,
  wine_lot_id CHAR(36) NULL,
  noted_at DATETIME(6) NOT NULL,
  note_type ENUM('observation','hypothesis','recommendation','decision','follow_up') NOT NULL,
  body MEDIUMTEXT NOT NULL,
  author_text VARCHAR(180) NULL,
  source ENUM('manual','chatgpt','home_assistant','import') NOT NULL DEFAULT 'manual',
  confirmed_fact TINYINT(1) NOT NULL DEFAULT 0,
  enologist_approval_required TINYINT(1) NOT NULL DEFAULT 0,
  approved_by VARCHAR(180) NULL,
  approved_at DATETIME(6) NULL,
  CONSTRAINT fk_lab_note_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_note_sample FOREIGN KEY (sample_id) REFERENCES lab_samples(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_note_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE VIEW v_lab_comparison AS
SELECT s.id sample_id,s.estate_id,s.sample_code,s.sample_name,s.sample_type,s.lab_date,s.sampled_at,
       se.vintage_year,b.code block_code,v.name variety_name,w.code wine_lot_code,w.stage wine_stage,
       r.id result_id,r.analyte_code,r.analyte_name,r.numeric_value,r.text_value,r.unit,r.flag,
       ref.target_min,ref.target_max,ref.review_below,ref.review_above,ref.source_reference,
       CASE
         WHEN r.numeric_value IS NULL THEN COALESCE(r.flag,'review')
         WHEN ref.review_below IS NOT NULL AND r.numeric_value<ref.review_below THEN 'review'
         WHEN ref.review_above IS NOT NULL AND r.numeric_value>ref.review_above THEN 'review'
         WHEN ref.target_min IS NOT NULL AND r.numeric_value<ref.target_min THEN 'low'
         WHEN ref.target_max IS NOT NULL AND r.numeric_value>ref.target_max THEN 'high'
         ELSE COALESCE(r.flag,'normal')
       END comparison_flag,
       lr.review_status,lr.interpretation,lr.decision_action,lr.decision_type,lr.owner_text,lr.next_check_at,
       lr.enologist_approval_required,lr.approved_by,lr.approved_at
FROM lab_samples s
LEFT JOIN seasons se ON se.id=s.season_id
LEFT JOIN vineyard_blocks b ON b.id=s.block_id
LEFT JOIN grape_varieties v ON v.id=s.variety_id
LEFT JOIN wine_lots w ON w.id=s.wine_lot_id
JOIN lab_results r ON r.sample_id=s.id
LEFT JOIN lab_reference_ranges ref ON ref.id=(
  SELECT rr.id FROM lab_reference_ranges rr
  WHERE rr.estate_id=s.estate_id AND rr.analyte_code=r.analyte_code AND rr.active=1
    AND (rr.sample_type IS NULL OR rr.sample_type=s.sample_type)
    AND (rr.stage IS NULL OR rr.stage=w.stage)
    AND (rr.effective_from IS NULL OR rr.effective_from<=s.lab_date)
    AND (rr.effective_to IS NULL OR rr.effective_to>=s.lab_date)
  ORDER BY (rr.sample_type IS NOT NULL) DESC,(rr.stage IS NOT NULL) DESC,rr.effective_from DESC LIMIT 1
)
LEFT JOIN lab_reviews lr ON lr.sample_id=s.id;

CREATE OR REPLACE VIEW v_lab_decision_queue AS
SELECT s.id sample_id,s.estate_id,s.lab_date,s.sample_name,s.sample_type,s.needs_review,s.review_notes,
       COALESCE(lr.review_status,'unreviewed') review_status,lr.owner_text,lr.next_check_at,
       SUM(CASE WHEN c.comparison_flag IN ('review','high','low') THEN 1 ELSE 0 END) flagged_results,
       COUNT(c.result_id) result_count
FROM lab_samples s
LEFT JOIN lab_reviews lr ON lr.sample_id=s.id
LEFT JOIN v_lab_comparison c ON c.sample_id=s.id
GROUP BY s.id,s.estate_id,s.lab_date,s.sample_name,s.sample_type,s.needs_review,s.review_notes,lr.review_status,lr.owner_text,lr.next_check_at;
