-- Reconcile one physical 10 kg crystalMUSTGRAPE addition that was recorded
-- twice. Retain the contemporaneous 17 September event (with supplied-label
-- evidence) and remove the later migration-created 24 September duplicate.

DELETE a
FROM enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
WHERE a.id='18300000-0000-4000-8000-000000000001'
  AND a.additive_name='crystalMUSTGRAPE'
  AND a.quantity=10.0000
  AND LOWER(a.unit)='kg';

UPDATE notes n
JOIN wine_lots w ON w.id=n.related_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET n.body=CONCAT(n.body,' Duplicate reconciliation: the later 24 September crystalMUSTGRAPE event was removed; the more complete 17 September 10 kg event remains authoritative.')
WHERE n.id='18300000-0000-4000-8000-000000000004'
  AND n.body NOT LIKE '%the more complete 17 September 10 kg event remains authoritative%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-186','reconcile_duplicate_grecanico_addition','wine_lot','GRC-2026-01-P',
       JSON_OBJECT('product','crystalMUSTGRAPE','physical_additions',1,'quantity_kg',10,
                   'retained_applied_date','2026-09-17','removed_event_id','18300000-0000-4000-8000-000000000001',
                   'reason','The later 24 September record duplicated the same owner-confirmed two-bag addition.')
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-186' AND a.action='reconcile_duplicate_grecanico_addition'
);
