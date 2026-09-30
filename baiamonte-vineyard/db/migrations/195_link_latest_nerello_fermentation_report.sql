-- The approved 30 September Nerello report arrived as generic "other" even
-- though its Natura is Mosto/Vino and it reports fermentation progress. Link
-- it to the only 2026 Nerello cellar lot and preserve the correction trail.

UPDATE lab_samples s
JOIN seasons se ON se.id=s.season_id AND se.vintage_year=2026
JOIN wine_lots w ON w.season_id=se.id AND w.code='NM-2026-01'
SET s.sample_type='wine',s.wine_lot_id=w.id,s.vintage_year=2026,
    s.vintage_assignment_source='wine_lot',s.vintage_assignment_confidence='confirmed',
    s.vintage_assignment_evidence='Exact 2026 Nerello cellar lot linked from the approved Mosto/Vino fermentation report.',
    s.review_notes=CONCAT_WS('\n',NULLIF(s.review_notes,''),'System correction 2026-09-30: reclassified other → wine and linked to NM-2026-01. This fermentation-progress report supersedes the 2026-09-26 baseline for current recipe calculations; the earlier report remains in history.')
WHERE s.lab_date='2026-09-30' AND LOWER(s.sample_name)='nerello mascalese'
  AND EXISTS (SELECT 1 FROM lab_results r WHERE r.sample_id=s.id AND r.analyte_code='total_alcohol');

INSERT INTO lab_sample_wine_lots (estate_id,sample_id,wine_lot_id,linked_by)
SELECT s.estate_id,s.id,w.id,'system correction 2026-09-30 · exact Mosto/Vino lot'
FROM lab_samples s JOIN seasons se ON se.id=s.season_id AND se.vintage_year=2026
JOIN wine_lots w ON w.season_id=se.id AND w.code='NM-2026-01'
WHERE s.lab_date='2026-09-30' AND LOWER(s.sample_name)='nerello mascalese'
  AND EXISTS (SELECT 1 FROM lab_results r WHERE r.sample_id=s.id AND r.analyte_code='total_alcohol')
ON DUPLICATE KEY UPDATE linked_by=VALUES(linked_by),linked_at=CURRENT_TIMESTAMP(6);

UPDATE lab_results r JOIN lab_samples s ON s.id=r.sample_id
SET r.analyte_mapping_status='static',r.analyte_mapping_checked_at=NOW(6)
WHERE s.lab_date='2026-09-30' AND LOWER(s.sample_name)='nerello mascalese'
  AND r.analyte_code='total_alcohol';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT s.estate_id,'migration-195','correct_latest_nerello_lab_link','lab_sample',s.id,
       JSON_OBJECT('sample_type','other','wine_lot_id',NULL),
       JSON_OBJECT('sample_type','wine','wine_lot_code','NM-2026-01','lab_date','2026-09-30',
                   'current_total_alcohol_pct',12.52,'developed_alcohol_pct',6.46,
                   'remaining_potential_alcohol_pct',6.06,'glucose_fructose_g_l',102,
                   'supersedes_for_current_recipe','2026-09-26 baseline')
FROM lab_samples s
WHERE s.lab_date='2026-09-30' AND LOWER(s.sample_name)='nerello mascalese'
  AND NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=s.estate_id AND a.actor='migration-195'
                  AND a.action='correct_latest_nerello_lab_link' AND a.entity_id=s.id);
