UPDATE estate_known_vehicles rental
JOIN (
  SELECT estate_id,
         SUM(confirmed_observations) AS confirmed_observations,
         MIN(first_seen_at) AS first_seen_at,
         MAX(last_seen_at) AS last_seen_at
  FROM estate_known_vehicles
  WHERE active=1
    AND person_entity='person.giancarlo'
    AND LOWER(COALESCE(vehicle_color,''))='white'
    AND id<>'16fceba8-4445-4fe0-b5e8-afd0783763e5'
  GROUP BY estate_id
) duplicate ON duplicate.estate_id=rental.estate_id
SET rental.confirmed_observations=rental.confirmed_observations+duplicate.confirmed_observations,
    rental.first_seen_at=LEAST(COALESCE(rental.first_seen_at,duplicate.first_seen_at),duplicate.first_seen_at),
    rental.last_seen_at=GREATEST(COALESCE(rental.last_seen_at,duplicate.last_seen_at),duplicate.last_seen_at),
    rental.notes='Temporary white Peugeot 4000 wagon rented by David during the 45 days before 2026-10-17. Historical exclusion only; never match it to Giancarlo or treat it as recurring.'
WHERE rental.identity_key=SHA2('historical-rental|david|white|peugeot|4000|wagon|2026-09',256);

UPDATE estate_vehicle_movements movement
JOIN estate_known_vehicles duplicate
  ON duplicate.estate_id=movement.estate_id
 AND duplicate.id=movement.known_vehicle_id
JOIN estate_known_vehicles rental
  ON rental.estate_id=movement.estate_id
 AND rental.identity_key=SHA2('historical-rental|david|white|peugeot|4000|wagon|2026-09',256)
SET movement.known_vehicle_id=rental.id,
    movement.staff_person_entity='person.david_rahamin',
    movement.staff_name='David Rahamin',
    movement.subject_category='other',
    movement.tag_label='Historical rental · white Peugeot 4000 wagon',
    movement.reviewed_by='owner_correction',
    movement.reviewed_at=NOW(6),
    movement.review_notes='Owner correction: this temporary white rental must not be attributed to Giancarlo or his silver Volkswagen Golf.'
WHERE duplicate.active=1
  AND duplicate.person_entity='person.giancarlo'
  AND LOWER(COALESCE(duplicate.vehicle_color,''))='white'
  AND duplicate.id<>'16fceba8-4445-4fe0-b5e8-afd0783763e5';

UPDATE estate_known_vehicles
SET active=0,
    person_entity=NULL,
    person_name=NULL,
    subject_category='other',
    display_name='Archived duplicate · white vehicle',
    notes='Archived by owner correction: duplicate identity was incorrectly attributed to Giancarlo. Historical movements were reassigned to David''s temporary white Peugeot rental.'
WHERE active=1
  AND person_entity='person.giancarlo'
  AND LOWER(COALESCE(vehicle_color,''))='white'
  AND id<>'16fceba8-4445-4fe0-b5e8-afd0783763e5';
