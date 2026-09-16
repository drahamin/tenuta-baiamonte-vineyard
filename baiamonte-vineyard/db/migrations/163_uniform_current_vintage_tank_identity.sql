-- Reconcile the three owner-confirmed 2026 cellar vessels to one physical
-- naming convention: stable vessel code plus a concise, title-cased name.
-- The container id and public label token remain unchanged, so lot history,
-- WhatsApp updates, pipelines and the installed tablet continue to point to
-- the same physical vessel.

UPDATE cellar_containers
SET code='T-03',
    name='Tank 3 · Grecanico 2026 · Primary'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND code='T-06'
  AND NOT EXISTS (
    SELECT 1 FROM (
      SELECT code FROM cellar_containers
      WHERE estate_id='00000000-0000-4000-8000-000000000001'
    ) existing_codes
    WHERE existing_codes.code='T-03'
  );

UPDATE cellar_containers
SET name='Tank 44 · Grecanico 2026 · Final Press'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND code='T-44';

UPDATE cellar_containers
SET name='Mustalone 500 L · Grenache 2026'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND code='M-01';

-- Historical readings used the former internal code as their vessel label.
-- Move that machine-facing alias with the physical tank while retaining all
-- source wording and timestamps in the observation notes.
UPDATE fermentation_observations
SET vessel_name='T-03'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vessel_name='T-06';

INSERT INTO audit_events
  (estate_id,action,entity_type,entity_id,after_data,actor)
SELECT
  c.estate_id,
  'reconcile_identity',
  'cellar_container',
  c.id,
  JSON_OBJECT(
    'previous_code','T-06',
    'code','T-03',
    'name',c.name,
    'reason','Owner-confirmed physical Tank 3; standardized 2026 digital-tag naming'
  ),
  'migration-163'
FROM cellar_containers c
WHERE c.estate_id='00000000-0000-4000-8000-000000000001'
  AND c.code='T-03'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events audit
    WHERE audit.estate_id=c.estate_id
      AND audit.actor='migration-163'
      AND audit.action='reconcile_identity'
      AND audit.entity_id=c.id
  );
