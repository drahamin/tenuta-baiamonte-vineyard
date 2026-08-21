-- Owner-confirmed carrier used with the primary removable GS sprayer group.

INSERT INTO equipment (id,estate_id,name,equipment_type,make_model,status,notes,active)
SELECT UUID(),e.id,'Blue Bird Carrier 500 H','crawler_carrier','Blue Bird Carrier 500 H · code 885160','available',
  'Owner-confirmed carrier for the removable primary GS 200 L sprayer group. Manufacturer: Loncin 196 cc, 6.5 hp, 3 forward/1 reverse transmission, 500 kg load capacity, hydraulic tipping box, 180 mm tracks with tensioning springs, 256.5 kg. Official source: https://www.bluebirdind.com/en/products/carrier-500-h/',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
  AND NOT EXISTS (SELECT 1 FROM equipment q WHERE q.estate_id=e.id AND q.make_model LIKE 'Blue Bird Carrier 500 H%');

UPDATE equipment q
JOIN estates e ON e.id=q.estate_id AND e.slug='tenuta-baiamonte'
SET q.notes=CONCAT(q.notes,' Mounted on owner-confirmed Blue Bird Carrier 500 H (code 885160), recorded as a separate estate asset.')
WHERE q.make_model='GS M2192017.1 · AR 252 · Honda GP160'
  AND q.notes NOT LIKE '%Blue Bird Carrier 500 H%';
