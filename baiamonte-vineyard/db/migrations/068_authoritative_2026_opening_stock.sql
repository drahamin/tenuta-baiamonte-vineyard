INSERT INTO app_settings (estate_id,setting_key,setting_value)
SELECT e.id,'treatment_stock_baseline','{"effective_on":"2026-01-01","opening_quantity":0,"confirmed_on":"2026-08-19","source":"owner confirmation","rule":"Stock was zero on 2026-01-01. Every Agriplanet invoice dated in 2026 adds stock on its invoice date. Matching invoice copies reconcile; additional recognized lines add stock; unfamiliar lines require classification. Confirmed usage subtracts separately."}'
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value),updated_at=NOW(6);
