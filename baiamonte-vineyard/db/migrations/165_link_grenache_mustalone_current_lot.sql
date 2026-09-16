-- The owner confirmed that the separate 2026 Grenache must is physically in
-- M-01. Link the exact wine lot to that vessel so its laboratory, process,
-- parcel and recipe context reaches the digital label and pipelines. Do not
-- set wine_lots.volume_l: the recorded 450 L is vessel occupancy with skins,
-- not measured pressed-juice volume.

UPDATE wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers c ON c.estate_id=w.estate_id AND c.code='M-01' AND c.active=1
SET w.current_container_id=c.id,
    w.stage='fermentation',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Owner-confirmed current vessel: M-01 Mustalone 500 L. The 90% / 450 L figure is pre-press occupancy including skins; pressed juice volume remains unmeasured.')
WHERE w.estate_id='00000000-0000-4000-8000-000000000001'
  AND w.code='GRN-2026-01'
  AND (w.current_container_id IS NULL OR w.current_container_id<>c.id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT w.estate_id,'migration-165','assign_current_vessel','wine_lot',w.id,
       JSON_OBJECT(
         'wine_lot_code',w.code,
         'container_code','M-01',
         'volume_policy','Keep pre-press occupancy separate from measured juice volume'
       )
FROM wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers c ON c.id=w.current_container_id AND c.code='M-01'
WHERE w.estate_id='00000000-0000-4000-8000-000000000001'
  AND w.code='GRN-2026-01'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events audit
    WHERE audit.estate_id=w.estate_id
      AND audit.actor='migration-165'
      AND audit.action='assign_current_vessel'
      AND audit.entity_id=w.id
  );
