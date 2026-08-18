ALTER TABLE vintage_summaries
  ADD COLUMN IF NOT EXISTS first_pick_date DATE NULL AFTER cassette_count,
  ADD COLUMN IF NOT EXISTS last_pick_date DATE NULL AFTER first_pick_date,
  ADD COLUMN IF NOT EXISTS harvest_date_precision ENUM('day','month','year','unknown') NOT NULL DEFAULT 'unknown' AFTER last_pick_date,
  ADD COLUMN IF NOT EXISTS source_note_id VARCHAR(190) NULL AFTER reconciliation_note,
  ADD COLUMN IF NOT EXISTS source_note_name VARCHAR(255) NULL AFTER source_note_id;

ALTER TABLE lab_samples
  ADD COLUMN IF NOT EXISTS vintage_year SMALLINT UNSIGNED NULL AFTER lab_date;

CREATE TABLE IF NOT EXISTS historical_note_facts (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_note_id VARCHAR(190) NOT NULL,
  source_note_name VARCHAR(255) NOT NULL,
  fact_key VARCHAR(190) NOT NULL,
  fact_date DATE NULL,
  fact_year SMALLINT UNSIGNED NULL,
  date_precision ENUM('day','month','year','unknown') NOT NULL DEFAULT 'unknown',
  domain VARCHAR(80) NOT NULL,
  subject VARCHAR(180) NOT NULL,
  quantity_value DECIMAL(16,3) NULL,
  quantity_unit VARCHAR(50) NULL,
  details MEDIUMTEXT NOT NULL,
  evidence_status VARCHAR(80) NOT NULL DEFAULT 'source_note',
  canonical_table VARCHAR(100) NULL,
  canonical_key VARCHAR(190) NULL,
  conflict_note TEXT NULL,
  source_modified_at DATETIME NULL,
  imported_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_historical_note_fact (estate_id,source_note_id,fact_key),
  KEY ix_historical_note_fact_year (estate_id,fact_year,domain),
  CONSTRAINT fk_historical_note_fact_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO vintage_summaries
  (estate_id,vintage_year,variety_name,grapes_kg,wine_l,cassette_count,evidence_status,reconciliation_note,source_note_id,source_note_name)
VALUES
  ('00000000-0000-4000-8000-000000000001',2022,'Grecanico',2700,1890,NULL,'Apple Notes','2022 variety total, 1,500 vines. Corroborated in Cellar Equipment and Tenuta Baiamonte - General Info.','p9750','Tenuta Baiamonte - General Info'),
  ('00000000-0000-4000-8000-000000000001',2022,'Nerello Mascalese',4900,3400,NULL,'Apple Notes','2022 variety total, 2,500 vines. Corroborated in Cellar Equipment and Tenuta Baiamonte - General Info.','p9750','Tenuta Baiamonte - General Info'),
  ('00000000-0000-4000-8000-000000000001',2022,'Grenache',400,280,NULL,'Apple Notes','2022 variety total, 250 vines. Corroborated in Cellar Equipment and Tenuta Baiamonte - General Info.','p9750','Tenuta Baiamonte - General Info'),
  ('00000000-0000-4000-8000-000000000001',2022,'Chardonnay',1,NULL,NULL,'Apple Notes','Two vines and 1 kg are recorded in Cellar Equipment, no wine volume is stated.','p10109','Cellar Equipment');

UPDATE vintage_summaries
SET first_pick_date='2025-09-23',
    last_pick_date='2025-09-23',
    harvest_date_precision='day',
    source_note_id='p21780',
    source_note_name='2025 Harvest Nerello 9/23',
    reconciliation_note=CONCAT_WS(' ',NULLIF(reconciliation_note,''),'Apple Notes confirms the Nerello pick on 2025-09-23: 8 people, 164 cassettes and 3,036 kg.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2025
  AND LOWER(TRIM(variety_name)) LIKE 'nerello%';

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,quantity_value,quantity_unit,details,evidence_status,canonical_table,canonical_key,conflict_note,source_modified_at)
VALUES
  ('44000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','p21780','2025 Harvest Nerello 9/23','nerello-harvest','2025-09-23',2025,'day','harvest','Nerello',3036,'kg','Eight people. Round 1: 07:30-11:16, 108 cassettes. Lunch: 12:00-13:00. Round 2: 13:00-15:15, 56 cassettes. Total: 164 cassettes and 3,036 kg.','confirmed_note','vintage_summaries','2025:Nerello',NULL,'2026-06-24 00:00:00'),
  ('44000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','p9750','Tenuta Baiamonte - General Info','2022-grecanico',NULL,2022,'year','harvest','Grecanico',2700,'kg','1,500 vines, 2,700 kg, 1,890 L, 2,520 bottle equivalents.','confirmed_note','vintage_summaries','2022:Grecanico',NULL,NULL),
  ('44000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000001','p9750','Tenuta Baiamonte - General Info','2022-nerello',NULL,2022,'year','harvest','Nerello Mascalese',4900,'kg','2,500 vines, 4,900 kg, 3,400 L, 4,530 bottle equivalents.','confirmed_note','vintage_summaries','2022:Nerello Mascalese',NULL,NULL),
  ('44000000-0000-4000-8000-000000000004','00000000-0000-4000-8000-000000000001','p9750','Tenuta Baiamonte - General Info','2022-grenache',NULL,2022,'year','harvest','Grenache',400,'kg','250 vines, 400 kg, 280 L, 373 bottle equivalents.','confirmed_note','vintage_summaries','2022:Grenache','The same note states a 7,500 kg total, which does not equal its variety figures. Variety figures are retained separately.',NULL),
  ('44000000-0000-4000-8000-000000000005','00000000-0000-4000-8000-000000000001','p10109','Cellar Equipment','2022-chardonnay',NULL,2022,'year','harvest','Chardonnay',1,'kg','Two vines and 1 kg, no wine volume stated.','confirmed_note','vintage_summaries','2022:Chardonnay',NULL,'2025-08-11 00:00:00'),
  ('44000000-0000-4000-8000-000000000006','00000000-0000-4000-8000-000000000001','p16840','Baiamonte 2023 Olive Oil Harvest','2023-olive-harvest','2023-10-30',2023,'day','olives','Olive harvest',1937,'kg','Harvest recorded across October 30-31, 2023. The note records 1,937 kg total olives and 233 L oil.','source_note',NULL,NULL,'The note also uses 1,337 kg for a first/press subset and calculates 5.73 kg/L from that subset.',NULL),
  ('44000000-0000-4000-8000-000000000007','00000000-0000-4000-8000-000000000001','p19081','2024 Baiamonte Olive Oil','2024-olive-yield',NULL,2024,'year','olives','Olive harvest',332,'kg','332 kg olives, primary yield line records 40 L oil.','source_note',NULL,NULL,'The note also states 44 L and packaging arithmetic totals 45 L. 40 L is retained as the primary yield line pending reconciliation.',NULL),
  ('44000000-0000-4000-8000-000000000008','00000000-0000-4000-8000-000000000001','p21500','Baiamonte 2025 Harvest','2025-olive-yield',NULL,2025,'year','olives','Olive harvest',1162,'kg','Two lots: 747 kg and 415 kg. Total raw oil 138.66 L, filtered oil 130 L. Packaging: 170 x 500 ml and 15 x 3 L.','confirmed_note',NULL,NULL,NULL,NULL),
  ('44000000-0000-4000-8000-000000000009','00000000-0000-4000-8000-000000000001','p16911','2023 Vintage Sales','2023-bottled',NULL,2023,'year','cellar','Bottled production',4658,'750ml bottles','White 2,370 plus 10 magnums, Nerello 1,986 plus 10 magnums, Grenache 302 plus 15 magnums.','source_note',NULL,NULL,'This is an actual bottled/sales count and differs from theoretical bottle-equivalent figures in the harvest summary.',NULL),
  ('44000000-0000-4000-8000-000000000010','00000000-0000-4000-8000-000000000001','p20877','2024 Vintage Sales','2024-bottled',NULL,2024,'year','cellar','Bottled production',2310,'750ml bottles','White 1,182 plus 6 magnums, Nerello 1,128 plus 6 magnums.','confirmed_note',NULL,NULL,NULL,NULL),
  ('44000000-0000-4000-8000-000000000011','00000000-0000-4000-8000-000000000001','p23070','Inventory','2026-inventory-snapshot','2026-02-25',2026,'day','inventory','Historical wine stock snapshot',NULL,NULL,'Snapshot: 101 cases white 2024, 100 plus 25 cases red 2024, 43 additional cases white 2024, 42 cases Nerello 2023 unlabeled, 192 plus 20 cases white 2023 unlabeled, 36 cases Grenache 2023 unlabeled, 96 cases white 2023 labeled in cellar, 96 cases red 2023 seized pallet, 35 mixed 2023/2024 magnums.','source_note',NULL,NULL,'Historical snapshot only, not used as current inventory.','2026-02-25 00:00:00'),
  ('44000000-0000-4000-8000-000000000012','00000000-0000-4000-8000-000000000001','p24061','Nunzio Work','2026-water-baseline',NULL,2026,'year','labor','Nunzio water deliveries',320,'EUR','Authoritative baseline in note: four deliveries x 5,000 L = 20,000 L, EUR 80 each, EUR 320.','confirmed_note','labor_entries','Nunzio:water-deliveries','A separate August 11 source says five deliveries/EUR 400 and requires Giancarlo confirmation before changing the baseline.',NULL),
  ('44000000-0000-4000-8000-000000000013','00000000-0000-4000-8000-000000000001','p24061','Nunzio Work','2026-excavator-work',NULL,2026,'year','labor','Nunzio excavator and transport',1660,'EUR','June 27: 9 h/EUR 360, July 11: 7 h/EUR 350, July 12: 6 h/EUR 300, July 24: 10 h/EUR 500, stone transport EUR 130.','source_note','labor_entries','Nunzio:excavator-2026',NULL,NULL),
  ('44000000-0000-4000-8000-000000000014','00000000-0000-4000-8000-000000000001','p18091','Baiamonte 2024 Harvest','2024-yield',NULL,2024,'year','harvest','2024 grape harvest',3220,'kg','White 1,662 kg, Nerello 1,558 kg, Grenache 0 kg. Later reconciled final wine: White 886 L and red 881 L.','confirmed_note','vintage_summaries','2024','The same note contains provisional 1,071 L white and 1,040 L Nerello. Later final liters remain authoritative.',NULL),
  ('44000000-0000-4000-8000-000000000015','00000000-0000-4000-8000-000000000001','p16869','Baiamonte 2023 Harvest','2023-yield',NULL,2023,'year','harvest','2023 grape harvest',5610,'kg','White 2,500 kg, Nerello 2,680 kg, Grenache 430 kg. Wine: 1,674 L, 1,794 L and 287 L respectively.','confirmed_note','vintage_summaries','2023',NULL,NULL)
ON DUPLICATE KEY UPDATE
  fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),
  quantity_value=VALUES(quantity_value),quantity_unit=VALUES(quantity_unit),details=VALUES(details),evidence_status=VALUES(evidence_status),
  canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key),conflict_note=VALUES(conflict_note),source_modified_at=VALUES(source_modified_at);

INSERT IGNORE INTO lab_samples
  (id,estate_id,season_id,sample_code,sample_name,sample_type,lab_date,laboratory,source_document,needs_review,review_notes,notes)
VALUES
  ('44000000-0000-4000-8000-000000000101','00000000-0000-4000-8000-000000000001',(SELECT id FROM seasons WHERE estate_id='00000000-0000-4000-8000-000000000001' AND vintage_year=2023 LIMIT 1),'APPLE-NOTES-2023-09-15','Baia Monte','grape','2023-09-15','CI.MA.LAB. SRLS','Apple Notes: Baiamonte Harvest 2023 - Lab Reports',1,'The report names the estate sample but not a grape variety. It is maturity evidence, not a confirmed harvest date.','pH 3.03, total acidity 8.4 g/L, 16.15 BABO, potential alcohol 10.65%.'),
  ('44000000-0000-4000-8000-000000000102','00000000-0000-4000-8000-000000000001',(SELECT id FROM seasons WHERE estate_id='00000000-0000-4000-8000-000000000001' AND vintage_year=2023 LIMIT 1),'APPLE-NOTES-2023-09-17-ALTO','Baia Monte - Alto','grape','2023-09-17','CI.MA.LAB. SRLS','Apple Notes: Baiamonte Harvest 2023 - Lab Reports',1,'The report identifies Alto but not a grape variety. It is maturity evidence, not a confirmed harvest date.','pH 3.03, total acidity 8.05 g/L, 16.71 BABO, potential alcohol 11.03%.'),
  ('44000000-0000-4000-8000-000000000103','00000000-0000-4000-8000-000000000001',(SELECT id FROM seasons WHERE estate_id='00000000-0000-4000-8000-000000000001' AND vintage_year=2023 LIMIT 1),'APPLE-NOTES-2023-09-17-BASSO','Baia Monte - Basso','grape','2023-09-17','CI.MA.LAB. SRLS','Apple Notes: Baiamonte Harvest 2023 - Lab Reports',1,'The report identifies Basso but not a grape variety. It is maturity evidence, not a confirmed harvest date.','pH 3.00, total acidity 9.55 g/L, 16.21 BABO, potential alcohol 10.70%.');

INSERT IGNORE INTO lab_results (id,sample_id,analyte_code,analyte_name,numeric_value,unit) VALUES
  ('44000000-0000-4000-8000-000000000201','44000000-0000-4000-8000-000000000101','ph','pH',3.03,NULL),
  ('44000000-0000-4000-8000-000000000202','44000000-0000-4000-8000-000000000101','ta','Total acidity',8.40,'g/L'),
  ('44000000-0000-4000-8000-000000000203','44000000-0000-4000-8000-000000000101','babo','BABO',16.15,'°BABO'),
  ('44000000-0000-4000-8000-000000000204','44000000-0000-4000-8000-000000000101','potential_alcohol','Potential alcohol',10.65,'% vol'),
  ('44000000-0000-4000-8000-000000000205','44000000-0000-4000-8000-000000000102','ph','pH',3.03,NULL),
  ('44000000-0000-4000-8000-000000000206','44000000-0000-4000-8000-000000000102','ta','Total acidity',8.05,'g/L'),
  ('44000000-0000-4000-8000-000000000207','44000000-0000-4000-8000-000000000102','babo','BABO',16.71,'°BABO'),
  ('44000000-0000-4000-8000-000000000208','44000000-0000-4000-8000-000000000102','potential_alcohol','Potential alcohol',11.03,'% vol'),
  ('44000000-0000-4000-8000-000000000209','44000000-0000-4000-8000-000000000103','ph','pH',3.00,NULL),
  ('44000000-0000-4000-8000-000000000210','44000000-0000-4000-8000-000000000103','ta','Total acidity',9.55,'g/L'),
  ('44000000-0000-4000-8000-000000000211','44000000-0000-4000-8000-000000000103','babo','BABO',16.21,'°BABO'),
  ('44000000-0000-4000-8000-000000000212','44000000-0000-4000-8000-000000000103','potential_alcohol','Potential alcohol',10.70,'% vol');

UPDATE lab_samples s
LEFT JOIN wine_lots w ON w.id=s.wine_lot_id
LEFT JOIN seasons wine_season ON wine_season.id=w.season_id
LEFT JOIN seasons assigned_season ON assigned_season.id=s.season_id
SET s.vintage_year=CASE
  WHEN wine_season.vintage_year IS NOT NULL THEN wine_season.vintage_year
  WHEN s.sample_type IN ('grape','must') THEN YEAR(s.lab_date)
  WHEN assigned_season.vintage_year IS NOT NULL THEN assigned_season.vintage_year
  ELSE YEAR(s.lab_date)
END
WHERE s.estate_id='00000000-0000-4000-8000-000000000001';

INSERT IGNORE INTO seasons (id,estate_id,vintage_year,status)
SELECT UUID(),s.estate_id,s.vintage_year,'closed'
FROM lab_samples s
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year IS NOT NULL
GROUP BY s.estate_id,s.vintage_year;

UPDATE lab_samples s
JOIN seasons correct_season ON correct_season.estate_id=s.estate_id AND correct_season.vintage_year=s.vintage_year
SET s.season_id=correct_season.id
WHERE s.estate_id='00000000-0000-4000-8000-000000000001'
  AND (s.season_id IS NULL OR s.season_id<>correct_season.id);
