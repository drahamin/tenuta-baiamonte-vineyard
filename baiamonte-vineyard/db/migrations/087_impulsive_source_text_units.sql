-- The structured Treatment 3 row was repaired by migration 086. Repair the
-- preserved human-readable source annotation as well so it cannot still imply
-- a mass measurement for liquid IMPULSIVE PREMIUM F.

UPDATE spray_applications
SET source_doses=REPLACE(source_doses,'IMPULSIVE PREMIUM: 450 ml/100 L (2,250 g total)','IMPULSIVE PREMIUM: 450 ml/100 L (2,250 ml total)')
WHERE estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)
  AND source_doses LIKE '%IMPULSIVE PREMIUM: 450 ml/100 L (2,250 g total)%';
