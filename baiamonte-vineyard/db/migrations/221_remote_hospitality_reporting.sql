-- Privacy-minimized hospitality reporting for the private remote ERP.
-- Deliberately exposes only the approved operational columns listed below.
CREATE OR REPLACE VIEW ro_hospitality_packages AS
SELECT
    id,
    estate_id,
    name,
    experience_type,
    description,
    duration_minutes,
    min_guests,
    max_guests,
    inclusions,
    active,
    sort_order,
    created_at,
    updated_at
FROM hospitality_packages;

CREATE OR REPLACE VIEW ro_hospitality_schedule AS
SELECT
    r.id,
    r.estate_id,
    r.confirmation_code,
    r.package_id,
    p.name AS package_name,
    p.experience_type,
    r.status,
    r.start_at,
    r.end_at,
    r.guest_count,
    r.preferred_language,
    r.source,
    r.assigned_manager_entity,
    r.created_at,
    r.updated_at
FROM hospitality_reservations r
LEFT JOIN hospitality_packages p
  ON p.id = r.package_id AND p.estate_id = r.estate_id;
