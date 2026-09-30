-- Restore the missing 2026 Nerello harvest-to-cellar trace.  BLOCK-NM-01 is
-- the registered estate Nerello source block. Its registry currently has no
-- elevation/soil values, so those facts remain visibly missing rather than
-- being invented.

UPDATE harvest_lots h
JOIN seasons s ON s.id=h.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=h.variety_id AND LOWER(v.name) LIKE 'nerello%'
JOIN vineyard_blocks b ON b.estate_id=h.estate_id AND b.code='BLOCK-NM-01'
SET h.block_id=b.id,
    h.notes=CONCAT_WS('\n',NULLIF(h.notes,''),'Trace correction 2026-09-30: linked to registered Nerello source block BLOCK-NM-01. Block altitude and soil remain unrecorded in the vineyard registry.')
WHERE h.lot_code='2026-NM-01' AND h.block_id IS NULL;

INSERT INTO cellar_lot_trace_records
  (id,estate_id,season_id,harvest_lot_id,wine_lot_id,container_id,transferred_at,fruit_kg,must_l,notes,recorded_by)
SELECT '19600000-0000-4000-8000-000000000001',h.estate_id,h.season_id,h.id,w.id,w.current_container_id,
       '2026-09-25 00:00:00',h.weight_kg,w.volume_l,
       'Restored exact-variety trace from 2026 Nerello harvest lot 2026-NM-01 / BLOCK-NM-01 to NM-2026-01 in T-09. Harvest and vessel dates are date-only; exact transfer time was not supplied.',
       'system trace repair 2026-09-30'
FROM harvest_lots h JOIN seasons s ON s.id=h.season_id AND s.vintage_year=2026
JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE h.lot_code='2026-NM-01' AND w.current_container_id IS NOT NULL
ON DUPLICATE KEY UPDATE harvest_lot_id=VALUES(harvest_lot_id),wine_lot_id=VALUES(wine_lot_id),
  container_id=VALUES(container_id),fruit_kg=VALUES(fruit_kg),must_l=VALUES(must_l),notes=VALUES(notes),recorded_by=VALUES(recorded_by);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-196','link_nerello_harvest_trace','wine_lot','NM-2026-01',
       JSON_OBJECT('harvest_lot','2026-NM-01','source_block','BLOCK-NM-01','cellar_container','T-09',
                   'elevation','not recorded','soil','not recorded','invented_values',FALSE)
FROM estates e WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-196'
  AND a.action='link_nerello_harvest_trace'
);
