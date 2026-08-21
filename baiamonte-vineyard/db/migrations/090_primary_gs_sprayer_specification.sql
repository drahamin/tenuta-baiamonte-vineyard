-- Owner-supplied Gruppi Scarrabili GS brochure identifies the primary 200 L
-- Mintransporter group and installed options. Rated pump figures are retained as
-- specifications, not promoted to a verified field calibration.

UPDATE equipment q
JOIN estates e ON e.id=q.estate_id AND e.slug='tenuta-baiamonte'
SET q.name='GS 200 L Mintransporter sprayer · M2192017.1',
    q.make_model='GS M2192017.1 · AR 252 · Honda GP160',
    q.notes='Owner-confirmed primary sprayer. Brochure row M2192017.1: 200 L polyethylene tank on painted steel frame, AR 252 pump, Honda GP160 engine, rated 25 L/min, 30 bar, 4.8 hp, 9-10 m throw, 50x100x75 cm and 49 kg. Installed options: M2400050 50 m 10x17 hose-reel assembly and M2030102.1 T-bar with 6 butterfly nozzles.'
WHERE q.equipment_type='sprayer' AND (q.make_model='Cingo M8' OR q.name='Cingo M8 tracked water sprayer');

UPDATE spray_equipment_profiles s
JOIN equipment q ON q.id=s.equipment_id
JOIN estates e ON e.id=s.estate_id AND e.slug='tenuta-baiamonte'
SET s.tank_capacity_l=200,
    s.nozzle_setup='M2030102.1 T-bar with 6 butterfly nozzles; M2400050 hose reel with 50 m 10x17 hose, 50 bar',
    s.source_reference='Owner-supplied Gruppi Scarrabili GS brochure · M2192017.1 + M2400050 + M2030102.1 · 2026-08-21',
    s.notes='Manufacturer ratings: AR 252 pump 25 L/min and maximum 30 bar. These are equipment specifications, not measured nozzle flow or operating pressure. Record usable fill, actual nozzle output, selected pressure, travel speed and carrier L/ha before marking calibration verified.',
    s.calibration_status=IF(s.calibration_status='verified','verified','needs_measurement')
WHERE q.make_model='GS M2192017.1 · AR 252 · Honda GP160';
