-- Sebastian is carrying both vineyard Agronomy and cellar Enology approval
-- responsibilities for the current operating year. Preserve the editable
-- person profile while correcting the role attached to his username.
UPDATE app_settings
SET setting_value = JSON_SET(
  setting_value,
  REPLACE(
    JSON_UNQUOTE(JSON_SEARCH(setting_value, 'one', 'sebastian', NULL, '$.*.username')),
    '.username',
    '.role'
  ),
  'Agronomist & Enologist'
)
WHERE setting_key = 'people_profiles'
  AND JSON_VALID(setting_value)
  AND JSON_SEARCH(setting_value, 'one', 'sebastian', NULL, '$.*.username') IS NOT NULL;
