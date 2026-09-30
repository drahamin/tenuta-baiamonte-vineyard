-- Owner-confirmed disposition on 30 September 2026: the Grecanico tail lot
-- was racked from its tank into three demijohns, moved to the vineyard, and
-- will age for drinking without further intervention.  The 275 L lot total is
-- retained; individual demijohn capacities/fills were not supplied.

INSERT INTO cellar_containers
  (id,estate_id,code,name,container_type,material,capacity_l,location,status,notes,active)
SELECT '19400000-0000-4000-8000-000000000001',s.estate_id,'DJ-GRC-T-SET',
       'Grecanico tail · 3 demijohns','demijohn','glass',COALESCE(w.volume_l,275.00),
       'Vineyard','in_use',
       'Logical vessel group for the three demijohns holding GRC-2026-01-T. Capacity is the recorded combined lot volume; individual demijohn capacities and fills were not supplied.',1
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE name=VALUES(name),container_type=VALUES(container_type),material=VALUES(material),
  capacity_l=VALUES(capacity_l),location=VALUES(location),status='in_use',notes=VALUES(notes),active=1;

INSERT INTO cellar_operations
  (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,notes)
SELECT '19400000-0000-4000-8000-000000000002',s.estate_id,s.id,w.id,d.id,
       '2026-09-30 00:00:00','Racking to vineyard demijohns',COALESCE(w.volume_l,275.00),'L',
       'Owner-confirmed transfer from the former tank into three demijohns, moved to the vineyard to age and then drink without further intervention. Date is confirmed; exact time and per-demijohn split were not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
JOIN cellar_containers d ON d.estate_id=s.estate_id AND d.code='DJ-GRC-T-SET'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE container_id=VALUES(container_id),operation_at=VALUES(operation_at),
  operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

UPDATE cellar_containers old_container
JOIN wine_lots w ON w.current_container_id=old_container.id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET old_container.status='empty',
    old_container.notes=CONCAT_WS('\n',NULLIF(old_container.notes,''),'GRC-2026-01-T racked out to three vineyard demijohns on 30 September 2026.')
WHERE w.code='GRC-2026-01-T' AND old_container.code<>'DJ-GRC-T-SET';

UPDATE cellar_control_profiles cp
JOIN wine_lots w ON w.current_container_id=cp.container_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET cp.manual_volume_l=0,cp.manual_contents=NULL,cp.manual_stage='empty',
    cp.manual_reading_at='2026-09-30 00:00:00',cp.manual_updated_at='2026-09-30 00:00:00',
    cp.updated_by='Owner disposition 2026-09-30'
WHERE w.code='GRC-2026-01-T' AND cp.container_id<>'19400000-0000-4000-8000-000000000001';

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers d ON d.estate_id=w.estate_id AND d.code='DJ-GRC-T-SET'
SET w.current_container_id=d.id,w.stage='aging',w.lot_status='aging_no_intervention',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'30 September 2026: racked into three demijohns and moved to the vineyard to age, then drink, with no further intervention planned. Recorded combined lot volume remains 275 L; individual demijohn fills were not supplied.')
WHERE w.code='GRC-2026-01-T'
  AND COALESCE(w.notes,'') NOT LIKE '%racked into three demijohns and moved to the vineyard%';

INSERT INTO cellar_control_profiles
  (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_reading_at,manual_updated_at,updated_by)
SELECT '19400000-0000-4000-8000-000000000003',d.estate_id,d.id,'manual','not_configured',
       'Grecanico 2026 tail wine · 3 demijohns',COALESCE(w.volume_l,275.00),'aging_no_intervention',
       '2026-09-30 00:00:00','2026-09-30 00:00:00','Owner disposition 2026-09-30'
FROM cellar_containers d JOIN wine_lots w ON w.current_container_id=d.id
WHERE d.code='DJ-GRC-T-SET' AND w.code='GRC-2026-01-T'
ON DUPLICATE KEY UPDATE manual_contents=VALUES(manual_contents),manual_volume_l=VALUES(manual_volume_l),
  manual_stage=VALUES(manual_stage),manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by);

UPDATE enology_process_profiles p
JOIN wine_lots w ON w.id=p.wine_lot_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET p.process_status='complete',
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),'Owner disposition 2026-09-30: aging in three vineyard demijohns; no further intervention planned.')
WHERE w.code='GRC-2026-01-T';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-194','close_grecanico_tail_in_demijohns','wine_lot','GRC-2026-01-T',
       JSON_OBJECT('stage','aging','lot_status','aging_no_intervention','location','Vineyard',
                   'vessel_group','DJ-GRC-T-SET','vessel_count',3,'combined_volume_l',275,
                   'individual_split','not supplied','further_intervention',FALSE)
FROM estates e WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-194'
  AND a.action='close_grecanico_tail_in_demijohns'
);
