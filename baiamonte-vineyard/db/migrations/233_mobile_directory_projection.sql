CREATE OR REPLACE SQL SECURITY INVOKER VIEW ro_mobile_directory AS
SELECT
  a.estate_id,
  SHA2(CONCAT(a.estate_id,'|',COALESCE(p.ha_user_id,p.username,p.display_name)),256) AS id,
  p.display_name,
  p.work_role,
  CASE
    WHEN LOWER(COALESCE(p.work_role,'')) LIKE '%agronom%' OR LOWER(COALESCE(p.work_role,'')) LIKE '%vineyard%' THEN 'Vineyard'
    WHEN LOWER(COALESCE(p.work_role,'')) LIKE '%enolog%' OR LOWER(COALESCE(p.work_role,'')) LIKE '%cellar%' THEN 'Cellar'
    WHEN LOWER(COALESCE(p.work_role,'')) LIKE '%hospitality%' THEN 'Hospitality'
    WHEN LOWER(COALESCE(p.work_role,'')) LIKE '%operation%' THEN 'Operations'
    ELSE 'Estate'
  END AS team,
  CASE WHEN p.access_level='none' THEN 0 ELSE 1 END AS active,
  a.updated_at
FROM app_settings a
JOIN JSON_TABLE(
  a.setting_value,
  '$.*' COLUMNS (
    display_name VARCHAR(120) PATH '$.name' NULL ON EMPTY,
    work_role VARCHAR(100) PATH '$.role' NULL ON EMPTY,
    access_level VARCHAR(40) PATH '$.access_level' NULL ON EMPTY,
    username VARCHAR(80) PATH '$.username' NULL ON EMPTY,
    ha_user_id VARCHAR(128) PATH '$.ha_user_id' NULL ON EMPTY
  )
) p
WHERE a.setting_key='people_profiles'
  AND p.display_name IS NOT NULL
  AND COALESCE(p.access_level,'none')<>'none';
