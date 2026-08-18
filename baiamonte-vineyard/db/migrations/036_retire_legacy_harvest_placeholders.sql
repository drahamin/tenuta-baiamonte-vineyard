UPDATE harvest_plans p
JOIN grape_varieties v ON v.id=p.variety_id AND v.estate_id=p.estate_id
SET p.status='cancelled',
    p.notes=CONCAT_WS(' ', NULLIF(TRIM(p.notes), ''), '[Retired legacy workbook placeholder: Blend and Other are not harvest varieties.]')
WHERE LOWER(TRIM(v.name)) IN ('blend','other')
  AND p.source_plan_id LIKE 'scheduled-harvest-%'
  AND p.approved_by IS NULL
  AND p.status IN ('draft','provisional','hold');

UPDATE grape_varieties
SET active=0,
    notes=CONCAT_WS(' ', NULLIF(TRIM(notes), ''), '[Retired legacy workbook placeholder. Blend production remains in the separate blend program.]')
WHERE LOWER(TRIM(name)) IN ('blend','other')
  AND active=1;
