-- Historical replays must respect both the per-hectare and tank-water
-- concentration limits recorded by the current label evidence.  These fields
-- are independent; a low carrier volume can otherwise turn a valid L/ha rate
-- into an excessive ml/hL concentration.
ALTER TABLE product_authorized_uses
  ADD COLUMN IF NOT EXISTS water_rate_min DECIMAL(12,3) NULL AFTER dose_unit,
  ADD COLUMN IF NOT EXISTS water_rate_max DECIMAL(12,3) NULL AFTER water_rate_min,
  ADD COLUMN IF NOT EXISTS water_rate_unit ENUM('g/L','g/100 L','ml/100 L') NULL AFTER water_rate_max;

UPDATE product_authorized_uses u JOIN products p ON p.id=u.product_id
SET u.water_rate_min=170,u.water_rate_max=420,u.water_rate_unit='ml/100 L'
WHERE p.name='OSSICLOR 20 BLU FLOW' AND u.crop_scope='vineyard' AND u.target_code='downy_mildew';
