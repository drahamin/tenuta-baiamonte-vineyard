-- Make authenticated enology entries immediately operational while retaining
-- quantity, unit, product-lot, timing, source-sheet and bench-trial controls.
UPDATE enology_additive_catalog
SET approval_required=0
WHERE estate_id='00000000-0000-4000-8000-000000000001';

UPDATE enology_product_protocols
SET prerequisites=REPLACE(REPLACE(REPLACE(prerequisites,
    ' and enologist approval',''),
    ', enologist approval',''),
    'enologist approval','authenticated operator record')
WHERE active=1;

-- Nutriferm Special is an inoculation nutrient in the current Enartis sheet.
-- Its 30-40 g/hL regular-fermentation range must not be presented as a
-- routine first-third addition. A stuck fermentation uses a distinct
-- 50 g/hL starter-culture protocol and is not calculated against total tank
-- volume here.
UPDATE enology_product_protocols r
JOIN enology_product_catalog p ON p.id=r.product_catalog_id
SET r.protocol_name='Inoculation nutrition',
    r.purpose='Support a measured nutrition need at yeast inoculation',
    r.process_stages='must,pre-fermentation',
    r.trigger_code='inoculation',
    r.dose_min=30,
    r.dose_max=40,
    r.dose_unit='g/hL',
    r.dose_basis='Official Enartis regular-fermentation range; 10 g/hL supplies approximately 16 mg/L YAN',
    r.preparation='Dissolve in a small amount of warm water and let stand for 15-20 minutes.',
    r.application_instructions='Add at yeast inoculation and homogenize. Account for approximately 16 mg/L YAN contribution per 10 g/hL and all other nitrogen additions.',
    r.prerequisites='Verified liquid volume, linked current YAN/APA, potential alcohol, turbidity, yeast selection and total nutrient accounting',
    r.incompatibilities='EU maximum 60 g/hL. The 50 g/hL stuck-fermentation use belongs in a starter culture, not as a direct whole-tank default.',
    r.source_revision='Official Enartis sheet and nutrient table checked 2026-09-16',
    r.verified_on='2026-09-16'
WHERE p.manufacturer='ENARTIS'
  AND p.normalized_name='nutriferm special'
  AND r.protocol_code='first_third';
