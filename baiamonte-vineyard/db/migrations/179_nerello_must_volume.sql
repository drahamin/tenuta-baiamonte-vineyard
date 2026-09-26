-- Owner visual/operational estimate for the active Nerello fermenter.
-- The vessel identity is still unknown, so only the lot volume is recorded.
UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.volume_l=1600.00,
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'26 September 2026: current Nerello must volume estimated at approximately 1,600 L; vessel identity remains pending.')
WHERE w.estate_id=s.estate_id AND w.code='NM-2026-01';

INSERT INTO cellar_operations
  (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes)
SELECT '17900000-0000-4000-8000-000000000001',s.estate_id,s.id,w.id,'2026-09-26 00:00:00',
       'Volume estimate',1600.000,'L','Owner reported the Nerello tank at approximately 1,600 L of must. Vessel identity and exact measurement time remain pending.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-179','record_volume_estimate','wine_lot','NM-2026-01',
       JSON_OBJECT('volume_l',1600,'precision','approximate','material','must','recorded_on','2026-09-26',
                   'q_grace_applied_g',500,'q_grace_observed_rate_g_hl',31.25,
                   'pending',JSON_ARRAY('vessel identity','exact measurement time','nutrient quantity'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-179' AND a.entity_id='NM-2026-01');
