-- Keep the treatment product catalog limited to agricultural inputs. Migration
-- 072 temporarily created reference profiles for every legacy `other` product,
-- which included grape varieties, vintage records, olives and finished oil.

UPDATE products
SET product_type='plant_protection'
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND name='OSSICLOR 20 BLU FLOW';

UPDATE treatment_product_profiles r
JOIN products p ON p.id=r.product_id AND p.estate_id=r.estate_id
SET r.active=0
WHERE p.estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND p.product_type='other';
