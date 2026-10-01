-- Make the current manufacturer catalog operational without turning it into a
-- one-product-per-category shopping list.  Every row below is tied to an
-- official manufacturer page or technical sheet and remains process/lab gated.

UPDATE enology_product_catalog
SET description='White-wine yeast for strong varietal expression, low-temperature or reductive fermentation. Official guidance: 10-20 C; below 15 C and below 70 NTU needs deliberate nitrogen and survival-factor management.',
    product_url='https://shop-usa.enartis.com/enartis-ferm-es-181',
    pds_url='https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermEs181.pdf',
    dose_min=20,dose_max=40,dose_unit='g/hL',dose_verified=1,
    dose_basis='Official Enartis ES181 technical sheet revision 6, 08/2025; higher rate only for rotten fruit, high sugar or difficult microbiology.',
    source_url='https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermEs181.pdf',source_checked_at=NOW(6)
WHERE manufacturer='ENARTIS' AND normalized_name='enartisferm es181';

UPDATE enology_product_protocols r
JOIN enology_product_catalog p ON p.id=r.product_catalog_id
SET r.purpose='Varietal white fermentation; an evidence fit for Grecanico when the target is aromatic precision without masking grape character',
    r.prerequisites='Verified volume, 10-20 C fermentation plan, current potential alcohol, YAN/APA, turbidity and one selected yeast; below 15 C or 70 NTU requires an explicit nutrition/survival plan',
    r.incompatibilities='Do not recommend merely from variety. Low-temperature/reductive fermentation must include measured nutrition and survival-factor management; this vigorous strain is not recommended for barrel fermentation.',
    r.source_url='https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-FermEs181.pdf',
    r.source_revision='Enartis ES181 technical sheet revision 6, 08/2025',r.verified_on='2026-10-01'
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartisferm es181' AND r.protocol_code='standard_inoculation';

UPDATE enology_product_catalog
SET description='Mediterranean red-wine yeast with explicit manufacturer affinity for Grenache, Carignan, Sangiovese, Mourvedre, Syrah and Merlot; supports fruit, suppleness, floral expression and glycerol.',
    product_url='https://laffort.com/en/products/zymaflore-f83/',
    pds_url='https://laffort.com/wp-content/uploads/FP/FP_FR_Zymaflore_F83.pdf',
    dose_min=15,dose_max=30,dose_unit='g/hL',dose_verified=1,
    dose_basis='Official LAFFORT product page and F83 technical sheet; 15-30 g/hL.',
    source_url='https://laffort.com/en/products/zymaflore-f83/',source_checked_at=NOW(6)
WHERE manufacturer='LAFFORT' AND normalized_name='zymaflore f83';

UPDATE enology_product_protocols r
JOIN enology_product_catalog p ON p.id=r.product_catalog_id
SET r.purpose='Fruit-forward, supple Mediterranean red fermentation; explicit manufacturer variety fit for Grenache',
    r.dose_min=15,r.dose_max=30,r.dose_unit='g/hL',
    r.dose_basis='Official LAFFORT F83 technical sheet range',
    r.prerequisites='Verified volume, red Mediterranean variety or matching style target, 20-30 C temperature plan, potential alcohol, YAN/APA and one selected yeast',
    r.source_url='https://laffort.com/wp-content/uploads/FP/FP_FR_Zymaflore_F83.pdf',
    r.source_revision='Official LAFFORT F83 sheet accessed 2026-10-01',r.verified_on='2026-10-01'
WHERE p.manufacturer='LAFFORT' AND p.normalized_name='zymaflore f83' AND r.protocol_code='standard_inoculation';

UPDATE enology_product_catalog
SET description='Mediterranean-style red and white yeast. Official Lallemand guidance emphasizes red-wine mid-palate volume, smooth tannin and fruit/spice; Grenache trials support color/polyphenol stability. Moderate nitrogen demand, 15-28 C, 16% alcohol tolerance.',
    product_url='https://www.lallemandwine.com/en/united-states/products/wine-yeasts/lalvin-icv-d254',
    pds_url='https://products.lallemandwine.com/storage/files/wine-yeasts/135-technical-datasheet-cp-1711099646.pdf',
    dose_min=20,dose_max=40,dose_unit='g/hL',dose_verified=1,
    source_url='https://www.lallemandwine.com/en/united-states/products/wine-yeasts/lalvin-icv-d254',source_checked_at=NOW(6)
WHERE manufacturer='LALLEMAND OENOLOGY' AND normalized_name='lalvin icv d254';

UPDATE enology_product_protocols r
JOIN enology_product_catalog p ON p.id=r.product_catalog_id
SET r.purpose='Mediterranean red fermentation where mid-palate volume, smooth tannin and fruit/spice fit the target; a Grenache-supported alternative, not an automatic Nerello choice',
    r.prerequisites='Verified volume, 15-28 C temperature plan, potential alcohol, YAN/APA, moderate-nitrogen nutrition plan and one selected yeast',
    r.incompatibilities='Variety/style fit ranks this option but never creates a yeast need or overrides the already selected/applied strain.',
    r.source_url='https://products.lallemandwine.com/storage/files/wine-yeasts/135-technical-datasheet-cp-1711099646.pdf',
    r.source_revision='Lallemand ICV D254 official page and technical sheet accessed 2026-10-01',r.verified_on='2026-10-01'
WHERE p.manufacturer='LALLEMAND OENOLOGY' AND p.normalized_name='lalvin icv d254' AND r.protocol_code='standard_inoculation';

UPDATE enology_product_catalog
SET description='Red-must fermentation adjunct combining soluble mannoproteins, grape-seed tannin and ellagitannin for color protection/stability, fruit persistence, softer mouthfeel and fermentation support. Not a routine addition.',
    product_url='https://www.enartis.com/',
    pds_url='https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-ProTinto.pdf',
    dose_min=15,dose_max=40,dose_unit='g/hL',dose_verified=1,
    dose_basis='Official Enartis purpose-specific ranges: 15-20 g/hL young wine; 20 g/hL color protection; 30-40 g/hL medium/long aging.',
    source_url='https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-ProTinto.pdf',source_checked_at=NOW(6)
WHERE manufacturer='ENARTIS' AND normalized_name='enartispro tinto';

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,required_lab_analytes,lab_max_age_days,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on)
SELECT UUID(),p.id,'ageworthy_red','Age-worthy red fermentation support',
       'Protect and stabilize color while building mouthfeel for a medium/long-aging red style','red','must,fermentation','crusher_or_fermentation',30,40,'g/hL',
       'Official Enartis medium/long storage range',
       'Disperse in water or must equal to ten times the product weight and homogenize.',
       'Add at the beginning of fermentation while filling the vessel, then homogenize with a pump-over.',
       'Verified volume, active early-fermentation window, structured/age-worthy style target and a recorded color/mouthfeel objective',
       'ph,total_acidity,potential_alcohol',7,
       'Do not add after the early fermentation gate or simply because the wine is red; young-wine use has a separate lower-rate protocol.',NULL,
       'https://www.enartis.com/datasheets/TECHNICAL-DATA-SHEET/EN/TDS-EN-ProTinto.pdf','EnartisPro Tinto revision 6, 02/2025','2026-10-01'
FROM enology_product_catalog p
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='enartispro tinto'
ON DUPLICATE KEY UPDATE protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),preparation=VALUES(preparation),application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),required_lab_analytes=VALUES(required_lab_analytes),lab_max_age_days=VALUES(lab_max_age_days),incompatibilities=VALUES(incompatibilities),source_url=VALUES(source_url),source_revision=VALUES(source_revision),verified_on=VALUES(verified_on),active=1;

UPDATE enology_product_catalog
SET description='Fermentation nutrient containing DAP, yeast hulls and cellulose. Official timing is one-third sugar depletion; it supports kinetics, alcohol tolerance and H2S prevention when the measured nutrition plan indicates it.',
    product_url='https://shop-usa.enartis.com/nutriferm-advance',
    dose_min=20,dose_max=40,dose_unit='g/hL',dose_verified=1,
    dose_basis='Official Enartis product page: 20-40 g/hL at one-third sugar depletion.',
    source_url='https://shop-usa.enartis.com/nutriferm-advance',source_checked_at=NOW(6)
WHERE manufacturer='ENARTIS' AND normalized_name='nutriferm advance';

INSERT INTO enology_product_protocols
  (id,product_catalog_id,protocol_code,protocol_name,purpose,wine_colors,process_stages,trigger_code,dose_min,dose_max,dose_unit,dose_basis,preparation,application_instructions,prerequisites,required_lab_analytes,lab_max_age_days,incompatibilities,minimum_contact_hours,source_url,source_revision,verified_on)
SELECT UUID(),p.id,'first_third','One-third fermentation nutrition',
       'Support sugar transport and fermentation completion when measured nutrition and trajectory indicate a need','any','fermentation','density_drop_30',20,40,'g/hL',
       'Official Enartis product page range',
       'Suspend in ten times its weight of warm water.',
       'Add at one-third sugar depletion and homogenize; record the dose in the total nutrient ledger.',
       'Verified volume, starting/current Babo or density, current YAN/APA, potential alcohol, yeast strain and all nutrient already applied',
       'yan,potential_alcohol',7,
       'Contains DAP. Do not repeat automatically, stack with other nitrogen products without total accounting, or use after its fermentation window has passed.',NULL,
       'https://shop-usa.enartis.com/nutriferm-advance','Official Enartis product page accessed 2026-10-01','2026-10-01'
FROM enology_product_catalog p
WHERE p.manufacturer='ENARTIS' AND p.normalized_name='nutriferm advance'
ON DUPLICATE KEY UPDATE protocol_name=VALUES(protocol_name),purpose=VALUES(purpose),wine_colors=VALUES(wine_colors),process_stages=VALUES(process_stages),trigger_code=VALUES(trigger_code),dose_min=VALUES(dose_min),dose_max=VALUES(dose_max),dose_unit=VALUES(dose_unit),dose_basis=VALUES(dose_basis),preparation=VALUES(preparation),application_instructions=VALUES(application_instructions),prerequisites=VALUES(prerequisites),required_lab_analytes=VALUES(required_lab_analytes),lab_max_age_days=VALUES(lab_max_age_days),incompatibilities=VALUES(incompatibilities),source_url=VALUES(source_url),source_revision=VALUES(source_revision),verified_on=VALUES(verified_on),active=1;

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-201','enrich_actionable_recipe_bases','enology_product_catalog','source-backed-recipe-bases',
       JSON_OBJECT('products',JSON_ARRAY('EnartisFerm ES181','ZYMAFLORE F83','LALVIN ICV D254','EnartisPro TINTO','NUTRIFERM ADVANCE'),
                   'policy','Variety and style rank products only after process and laboratory gates establish need; no product-per-category recommendation.',
                   'sources_checked_on','2026-10-01')
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-201' AND a.action='enrich_actionable_recipe_bases');
