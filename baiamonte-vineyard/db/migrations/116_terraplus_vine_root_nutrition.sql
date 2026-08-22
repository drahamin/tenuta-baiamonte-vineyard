-- TERRAPLUS is a vineyard nutrition product delivered through fertigation or
-- localized root-zone application. It is neither a broadcast land/soil input
-- nor a foliar canopy treatment.
ALTER TABLE products
  MODIFY COLUMN fertilizer_application_route
  ENUM('land','vine_root','foliar','multi','unclassified')
  NOT NULL DEFAULT 'unclassified';

UPDATE products
SET fertilizer_application_route='vine_root',
    notes='Vine root nutrition: water-soluble organic NPK 8-7-6 for vineyard fertigation or localized root-zone application at the current approved rate. Do not classify as a broadcast soil/land product and do not spray the canopy.'
WHERE name='TERRAPLUS SOLUB NPK 8-7-6';
