-- Preserve reported laboratory values while attaching reusable, validated AI mappings.
CREATE TABLE IF NOT EXISTS enology_analyte_mappings (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_code_key VARCHAR(120) NOT NULL,
  source_name_key VARCHAR(200) NOT NULL,
  source_unit_key VARCHAR(80) NOT NULL,
  canonical_code VARCHAR(80) NOT NULL,
  canonical_name VARCHAR(160) NOT NULL,
  canonical_unit VARCHAR(80) NOT NULL,
  conversion_multiplier DECIMAL(20,10) NOT NULL DEFAULT 1,
  confidence DECIMAL(5,4) NOT NULL,
  mapping_source VARCHAR(40) NOT NULL DEFAULT 'openai_validated',
  model_version VARCHAR(120) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_analyte_source (estate_id,source_code_key,source_name_key,source_unit_key),
  KEY ix_enology_analyte_canonical (estate_id,canonical_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE lab_results
  ADD COLUMN IF NOT EXISTS analyte_mapping_id CHAR(36) NULL AFTER analyte_name;

ALTER TABLE lab_results
  ADD COLUMN IF NOT EXISTS analyte_mapping_status VARCHAR(30) NOT NULL DEFAULT 'pending' AFTER analyte_mapping_id;

ALTER TABLE lab_results
  ADD COLUMN IF NOT EXISTS analyte_mapping_checked_at DATETIME(6) NULL AFTER analyte_mapping_status;

ALTER TABLE lab_results
  ADD KEY IF NOT EXISTS ix_lab_result_analyte_mapping (analyte_mapping_id);

ALTER TABLE lab_results
  ADD KEY IF NOT EXISTS ix_lab_result_mapping_status (analyte_mapping_status,analyte_mapping_checked_at);
