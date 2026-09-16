-- A retired setup placeholder still occupied T-03 and correctly prevented
-- migration 163 from reusing the code. Preserve that retired row under an
-- explicit archive code, then give the owner-confirmed physical Tank 3 its
-- real code. Stable ids, lot links and public label tokens do not change.

UPDATE cellar_containers
SET code='ARCHIVE-T-03',
    name='Retired Fermenter 3 · Legacy Placeholder'
WHERE id='b125e0fc-9dd2-406b-b8e7-63ed935ff7ad'
  AND estate_id='00000000-0000-4000-8000-000000000001'
  AND code='T-03'
  AND active=0;

UPDATE cellar_containers
SET code='T-03',
    name='Tank 3 · Grecanico 2026 · Primary'
WHERE id='05dd268e-89fd-4b1c-b486-cb19c95274eb'
  AND estate_id='00000000-0000-4000-8000-000000000001'
  AND code='T-06'
  AND active=1;

UPDATE fermentation_observations
SET vessel_name='T-03'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vessel_name='T-06';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT c.estate_id,'migration-164','reconcile_identity','cellar_container',c.id,
       JSON_OBJECT(
         'previous_code','T-06',
         'code','T-03',
         'name',c.name,
         'retired_collision_code','ARCHIVE-T-03',
         'reason','Owner-confirmed physical Tank 3; retired setup placeholder preserved under an archive code'
       )
FROM cellar_containers c
WHERE c.id='05dd268e-89fd-4b1c-b486-cb19c95274eb'
  AND c.estate_id='00000000-0000-4000-8000-000000000001'
  AND c.code='T-03'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events audit
    WHERE audit.estate_id=c.estate_id
      AND audit.actor='migration-164'
      AND audit.action='reconcile_identity'
      AND audit.entity_id=c.id
  );
