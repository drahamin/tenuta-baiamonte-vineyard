CREATE TABLE IF NOT EXISTS vintage_designation_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NULL,
  plan_code VARCHAR(80) NOT NULL,
  wine_name VARCHAR(190) NOT NULL,
  designation_code VARCHAR(80) NOT NULL,
  designation_label VARCHAR(190) NOT NULL,
  decision_status ENUM('draft','locked','retired') NOT NULL DEFAULT 'draft',
  legal_review_status ENUM('simulation','review_required','verified','rejected') NOT NULL DEFAULT 'review_required',
  components_json LONGTEXT NOT NULL,
  simulation_json LONGTEXT NOT NULL,
  projected_grapes_kg DECIMAL(12,3) NOT NULL DEFAULT 0,
  projected_wine_l DECIMAL(12,3) NOT NULL DEFAULT 0,
  projected_bottles_750ml INT UNSIGNED NOT NULL DEFAULT 0,
  notes TEXT NULL,
  locked_by VARCHAR(190) NULL,
  locked_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_vintage_designation_plan_code (season_id,plan_code),
  KEY ix_vintage_designation_plan_status (estate_id,season_id,decision_status),
  CONSTRAINT fk_vintage_designation_plan_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_vintage_designation_plan_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_vintage_designation_plan_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE wine_lots
  ADD COLUMN IF NOT EXISTS designation_intent VARCHAR(80) NULL AFTER variety_summary,
  ADD COLUMN IF NOT EXISTS designation_label VARCHAR(190) NULL AFTER designation_intent,
  ADD COLUMN IF NOT EXISTS designation_decision_status VARCHAR(40) NULL AFTER designation_label,
  ADD COLUMN IF NOT EXISTS blend_components_text TEXT NULL AFTER designation_decision_status,
  ADD COLUMN IF NOT EXISTS designation_source_note TEXT NULL AFTER blend_components_text;

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT UUID(),s.estate_id,NOW(6),'2026 designation planning update',
       'Owner superseded the September separate-varietal-only planning rule. The final red wine may blend Nerello Mascalese with Grenache under a compatible designation. Etna DOC Rosso remains a separate selectable plan and must satisfy the official composition, origin, yield, traceability and certification requirements; selecting or locking a plan is not legal entitlement.',
       JSON_ARRAY('owner-decision','enology','designation','blend','2026'),'season',s.id
FROM seasons s
WHERE s.vintage_year=2026
  AND NOT EXISTS (SELECT 1 FROM notes n WHERE n.estate_id=s.estate_id AND n.title='2026 designation planning update');

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT UUID(),s.estate_id,'2026-10-24 12:52:35','Sebastian 2026 cellar reconciliation — transcription requires review',
       'Source: Sebastian handwritten cellar reconciliation, photographed 24 Oct 2026. Clear working volumes: Alicante 1 250 L cleaned; Alicante 2 385 L (cleaning wording unclear); Nerello 1 1,640 L cleaned; Nerello 2 300 L cleaned. Arithmetic shown: Alicante about 846 full 750 ml bottles; Nerello 1 about 2,186 bottles. Nerello 2 is noted separately and appears intended to fill Alicante 1 + Alicante 2. Grecanico shows 1,550 L in one place but its handwritten bottle calculation is inconsistent/unclear and must be confirmed before changing actual production. Use measured cleaned liquid as actual; treat kg-to-liter and bottle figures as calculations until confirmed.',
       JSON_ARRAY('source-evidence','enology','reconciliation','sebastian','review-required'),'season',s.id
FROM seasons s
WHERE s.vintage_year=2026
  AND NOT EXISTS (SELECT 1 FROM notes n WHERE n.estate_id=s.estate_id AND n.title='Sebastian 2026 cellar reconciliation — transcription requires review');
