-- Treatment 5 has owner-confirmed product quantities and carrier water, but
-- the overall application must remain open until its operator, exact scope,
-- calibration, weather, PPE and PHI/REI evidence are confirmed.
UPDATE spray_applications
SET operator_name=NULL,
    actual_details_confirmed=0,
    evidence_status='owner-confirmed application, water volume, products and per-100-L rates; scope, operator and safety details pending'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND crop_scope='vineyard'
  AND LOWER(TRIM(purpose))='treatment 5'
  AND status='completed'
  AND DATE(application_date)='2026-06-27'
  AND water_volume_l=400;
