ALTER TABLE lab_samples
  ADD COLUMN IF NOT EXISTS vintage_assignment_source VARCHAR(80) NULL AFTER vintage_year,
  ADD COLUMN IF NOT EXISTS vintage_assignment_confidence ENUM('confirmed','inferred','review_required') NOT NULL DEFAULT 'review_required' AFTER vintage_assignment_source,
  ADD COLUMN IF NOT EXISTS vintage_assignment_evidence VARCHAR(700) NULL AFTER vintage_assignment_confidence;

UPDATE lab_samples
SET vintage_assignment_source=CASE
      WHEN wine_lot_id IS NOT NULL THEN 'wine_lot'
      WHEN sample_type IN ('grape','must') THEN 'report_date'
      ELSE 'historical_import'
    END,
    vintage_assignment_confidence=CASE
      WHEN wine_lot_id IS NOT NULL OR sample_type IN ('grape','must') THEN 'confirmed'
      ELSE 'inferred'
    END,
    vintage_assignment_evidence=CASE
      WHEN wine_lot_id IS NOT NULL THEN 'Vintage inherited from the linked wine lot.'
      WHEN sample_type IN ('grape','must') THEN 'Fruit and must report belongs to the harvest year shown by its laboratory date.'
      ELSE 'Historical import assignment retained pending source-specific evidence.'
    END
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_assignment_source IS NULL;

UPDATE lab_samples
SET vintage_assignment_source='source_workbook',
    vintage_assignment_confidence='confirmed',
    vintage_assignment_evidence='The canonical laboratory audit workbook explicitly states the vintage.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND sample_code LIKE 'LAB-%'
  AND sample_code NOT IN (
    'LAB-20240507-01','LAB-20240507-02','LAB-20240507-03',
    'LAB-20250509-01','LAB-20250509-02','LAB-20250509-03','LAB-20250509-04','LAB-20250509-05','LAB-20250509-06',
    'LAB-20251027-01','LAB-20251027-02'
  );

UPDATE lab_samples s
JOIN seasons correct_season
  ON correct_season.estate_id=s.estate_id AND correct_season.vintage_year=2023
SET s.vintage_year=2023,
    s.season_id=correct_season.id,
    s.vintage_assignment_source='cellar_chronology',
    s.vintage_assignment_confidence='inferred',
    s.vintage_assignment_evidence='The CI.MA.LAB report leaves Annata blank. It is a wine report dated before the 2024 harvest, so it belongs to the preceding 2023 cellar vintage.'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001'
  AND s.sample_code IN ('LAB-20240507-01','LAB-20240507-02','LAB-20240507-03');

UPDATE lab_samples s
JOIN seasons correct_season
  ON correct_season.estate_id=s.estate_id AND correct_season.vintage_year=2023
SET s.vintage_year=2023,
    s.season_id=correct_season.id,
    s.vintage_assignment_source='sample_identity',
    s.vintage_assignment_confidence='inferred',
    s.vintage_assignment_evidence='The CI.MA.LAB report leaves Annata blank. Sample IDs G 1-G 3 and N 1-N 3 exactly match the 24 April 2025 report that explicitly identifies those wines as vintage 2023.'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001'
  AND s.sample_code IN ('LAB-20250509-01','LAB-20250509-02','LAB-20250509-03','LAB-20250509-04','LAB-20250509-05','LAB-20250509-06');

UPDATE lab_samples
SET vintage_assignment_source='cellar_chronology',
    vintage_assignment_confidence='inferred',
    vintage_assignment_evidence='The CI.MA.LAB report leaves Annata blank. The malolactic sequence falls between the October 2025 harvest reports and the November reports whose samples are explicitly labeled 25.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND sample_code IN ('LAB-20251027-01','LAB-20251027-02');

UPDATE lab_samples
SET vintage_assignment_source='source_report',
    vintage_assignment_confidence='confirmed',
    vintage_assignment_evidence='The source record explicitly states the vintage.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND (notes LIKE '%vintage shown on report is 2025%'
       OR sample_name REGEXP '(^|[^0-9])(20)?(23|24|25)([^0-9]|$)');

CREATE OR REPLACE VIEW v_lab_comparison AS
SELECT s.id sample_id,s.estate_id,s.sample_code,s.sample_name,s.sample_type,s.lab_date,s.sampled_at,
       COALESCE(s.vintage_year,se.vintage_year) vintage_year,s.vintage_assignment_source,s.vintage_assignment_confidence,s.vintage_assignment_evidence,
       b.code block_code,v.name variety_name,w.code wine_lot_code,w.stage wine_stage,
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
