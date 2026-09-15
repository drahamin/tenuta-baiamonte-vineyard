-- One representative must sample may legitimately govern multiple separated
-- fractions from the same must. Preserve one laboratory result and associate
-- it with each exact wine lot instead of duplicating the sample.
CREATE TABLE IF NOT EXISTS lab_sample_wine_lots (
  estate_id CHAR(36) NOT NULL,
  sample_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  linked_by VARCHAR(160) NULL,
  linked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sample_id,wine_lot_id),
  INDEX idx_lab_sample_wine_lots_lot (estate_id,wine_lot_id,sample_id),
  CONSTRAINT fk_lab_sample_wine_lots_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_sample_wine_lots_sample FOREIGN KEY (sample_id) REFERENCES lab_samples(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_sample_wine_lots_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO lab_sample_wine_lots (estate_id,sample_id,wine_lot_id,linked_by)
SELECT sample.estate_id,sample.id,lot.id,'David Rahamin · shared Grecanico must confirmation'
FROM lab_samples sample
JOIN lab_results result ON result.sample_id=sample.id AND LOWER(result.analyte_code)='apa' AND result.numeric_value=124
JOIN wine_lots lot ON lot.estate_id=sample.estate_id AND lot.season_id=sample.season_id
  AND lot.code IN ('GRC-2026-01-P','GRC-2026-01-T')
WHERE sample.lab_date='2026-09-11'
  AND sample.sample_type='must'
  AND LOWER(sample.sample_name)='mosto d uva bt grecanico';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT sample.estate_id,'migration-160','link_shared_must','lab_sample',sample.id,
       JSON_OBJECT('apa_mg_l',124,'wine_lots',JSON_ARRAY('GRC-2026-01-P','GRC-2026-01-T'),
                   'basis','Owner confirmed this must sample applies to both primary and final-press Grecanico wine')
FROM lab_samples sample
JOIN lab_results result ON result.sample_id=sample.id AND LOWER(result.analyte_code)='apa' AND result.numeric_value=124
WHERE sample.lab_date='2026-09-11' AND sample.sample_type='must'
  AND LOWER(sample.sample_name)='mosto d uva bt grecanico'
  AND NOT EXISTS (SELECT 1 FROM audit_events audit WHERE audit.estate_id=sample.estate_id AND audit.actor='migration-160' AND audit.entity_id=sample.id);
