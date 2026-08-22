-- Keep land/soil fertilizer procurement separate from foliar vine-treatment
-- products. This is an explicit catalog classification, not an inference from
-- the generic fertilizer product type.
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS fertilizer_application_route ENUM('land','foliar','multi','unclassified')
  NOT NULL DEFAULT 'unclassified' AFTER product_type;

UPDATE products
SET fertilizer_application_route='land'
WHERE name IN ('NOVATEC CLASSIC 12-8-16','TERRAPLUS SOLUB NPK 8-7-6');

UPDATE products
SET fertilizer_application_route='foliar'
WHERE name IN ('IMPULSIVE PREMIUM','RESOLVE','GEL DI SILICE','FRONTIERE','REPENTE','FERTICUS 18 M');
