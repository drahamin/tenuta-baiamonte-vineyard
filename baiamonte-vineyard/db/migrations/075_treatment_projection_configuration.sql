ALTER TABLE treatment_product_options
  ADD COLUMN IF NOT EXISTS maximum_rate_per_ha DECIMAL(12,3) NULL AFTER minimum_rate_per_ha,
  ADD COLUMN IF NOT EXISTS maximum_rate_per_ha_unit ENUM('kg/ha','L/ha') NULL AFTER minimum_rate_per_ha_unit;

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.minimum_rate_per_ha=2,o.maximum_rate_per_ha=3,
    o.minimum_rate_per_ha_unit='L/ha',o.maximum_rate_per_ha_unit='L/ha'
WHERE p.name='IMPULSIVE PREMIUM' AND o.crop_scope='vineyard';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.minimum_rate_per_ha=1,o.maximum_rate_per_ha=3,
    o.minimum_rate_per_ha_unit='L/ha',o.maximum_rate_per_ha_unit='L/ha'
WHERE p.name='REPENTE' AND o.crop_scope='vineyard';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.maximum_rate_per_ha=2,o.maximum_rate_per_ha_unit='kg/ha'
WHERE p.name='RESOLVE' AND o.crop_scope='vineyard' AND o.minimum_rate_per_ha=2;
