-- Complete current, source-backed vineyard directions for products that were
-- deliberately held out of projections until a manufacturer direction was found.

UPDATE products
SET product_type='fertilizer',unit='L',supplier='BioAtlantis / Kalos',
    notes='K&A FRONTIERE 2.0 liquid biostimulant/organic nitrogen fertilizer. Current manufacturer directions: vineyard foliar application 0.75-1.00 L/ha from vegetative awakening throughout the crop cycle. It is support, not a plant-protection substitute.'
WHERE name='FRONTIERE';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.measure_unit='L',r.verification_status='verified',
    r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_instructions='Dilute for foliar application at 0.75 to 1.00 L/ha. Use only for a documented support need and follow the current container directions.',
    r.compatibility_notes='The manufacturer states that it may be used alone or in mixture, but the estate system must not combine it automatically. Confirm the exact products and sequence with the Agronomist before any tank mix.',
    r.label_verified_on='2026-08-20',
    r.label_url='https://news.kalosgate.com/hubfs/Catalogo%20Prodotti%20KEA/induttori/Copia%20di%20Locandina%20FRONTIERE%202.0_ALTA.pdf',
    r.eligible_for_projection=1,
    r.source_summary='Current K&A manufacturer directions verify a liquid foliar vineyard rate of 0.75 to 1.00 L/ha from vegetative awakening through the crop cycle.'
WHERE p.name='FRONTIERE';

-- The option schema originally distinguished only g/L and ml/100 L. Add the
-- exact manufacturer unit before storing Ferticus so mass is never presented
-- as liquid volume.
ALTER TABLE treatment_product_options
  MODIFY COLUMN water_rate_unit ENUM('g/L','g/100 L','ml/100 L') NULL;

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.default_decision='not_selected',
    o.selection_conditions='Select only for a documented biostimulant/support need; vineyard foliar rate is 0.75 to 1.00 L/ha from vegetative awakening throughout the crop cycle. Agronomist approval remains required.',
    o.exclusion_reason='A disease-risk signal alone does not justify automatic addition.',
    o.minimum_rate_per_ha=.75,o.maximum_rate_per_ha=1,
    o.minimum_rate_per_ha_unit='L/ha',o.maximum_rate_per_ha_unit='L/ha',
    o.compatibility_status='conditional',
    o.compatibility_conditions='Do not combine automatically. Confirm the exact products, current directions and sequence with the Agronomist before any tank mix.'
WHERE p.name='FRONTIERE' AND o.crop_scope='vineyard';

UPDATE products
SET product_type='fertilizer',unit='kg',supplier='Manica',active_ingredient='Copper 18%; manganese 0.5%',
    notes='FERTICUS 18 M wettable-powder foliar micronutrient fertilizer. Current Manica directions for vineyard: 300-500 g/hL (300-500 g per 100 L). Use only for a recognized copper/manganese nutritional need; not automatic disease control.'
WHERE name='FERTICUS 18 M';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='wettable_powder',r.formulation_code='WP',r.measure_unit='kg',
    r.verification_status='verified',r.estate_authorization_status='confirmed',
    r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_position=20,
    r.mixing_instructions='Add the wettable powder gradually to water under continuous agitation. Vineyard foliar direction is 300 to 500 g per 100 L. Use only for a recognized need and do not exceed the appropriate dose.',
    r.compatibility_notes='Manufacturer material says it is miscible with wettable sulfur and common fertilizers and crop-protection products. The estate system still requires exact-product compatibility and Agronomist approval before combining.',
    r.label_verified_on='2026-08-20',r.label_url='https://www.manica.com/pdf/area-download/catalogomanica.pdf',
    r.eligible_for_projection=1,
    r.source_summary='Current Manica manufacturer catalogue verifies wettable powder, copper 18%, manganese 0.5%, and vineyard foliar rate 300-500 g/hL.'
WHERE p.name='FERTICUS 18 M';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.default_decision='not_selected',
    o.selection_conditions='Select only for a recognized copper or manganese nutritional need. Vineyard foliar rate is 300 to 500 g per 100 L; follow the current label and obtain Agronomist approval.',
    o.exclusion_reason='This is a micronutrient fertilizer, not an automatic disease-control product.',
    o.water_rate_min=300,o.water_rate_max=500,o.water_rate_unit='g/100 L',
    o.compatibility_status='conditional',
    o.compatibility_conditions='The recorded rate is a MASS rate (g/100 L), despite the legacy option column name. Do not combine automatically; verify exact-product compatibility and sequence with the Agronomist.'
WHERE p.name='FERTICUS 18 M' AND o.crop_scope='vineyard';

-- TerraPlus is supported by a vineyard-specific manufacturer sheet for
-- fertigation and localized soil spraying. It is enabled only as a
-- soil-directed nutritional spray, never as a foliar/canopy treatment.
UPDATE products
SET product_type='fertilizer',unit='kg',supplier='COMPO EXPERT',
    active_ingredient='Organic NPK 8-7-6; MgO 2%; free amino acids 18%',
    notes='TerraPlus Solub NPK 8-7-6 water-soluble organic fertilizer. Current vineyard manufacturer direction: 15-30 kg/ha per pass through fertigation or localized soil spraying. Do not apply as a foliar/canopy treatment; do not mix calcium into or acidify the mother solution.'
WHERE name='TERRAPLUS SOLUB NPK 8-7-6';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='water_soluble_powder',r.measure_unit='kg',
    r.final_application_medium='water_spray',r.verification_status='verified',
    r.estate_authorization_status='confirmed',r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_position=20,
    r.mixing_instructions='Localized soil spray only. Cover the powder with water and allow it to wet for several hours, then fill the tank while maintaining agitation. Apply 15 to 30 kg/ha per pass to the soil; do not spray the canopy.',
    r.compatibility_notes='Do not mix calcium into the mother solution and do not acidify it. Do not combine automatically with a plant-protection spray. Keep this as a separate, soil-directed nutrition pass unless the current directions and Agronomist explicitly approve otherwise.',
    r.water_quality_notes='Recommended mother-solution dissolution is 60-90 kg/1000 L, maximum 10%. Verify water quality and equipment before preparation.',
    r.label_verified_on='2026-08-20',
    r.label_url='https://www.compo-expert.com/sites/default/files/2022-09/TerraPlus%20Solub%20NPK_VIGNE_%28pc%29_France.pdf',
    r.eligible_for_projection=1,
    r.source_summary='COMPO EXPERT vineyard directions verify 15-30 kg/ha per pass and permit localized soil spraying. This does not authorize foliar/canopy application.'
WHERE p.name='TERRAPLUS SOLUB NPK 8-7-6';

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.default_decision='not_selected',
    o.selection_conditions='Select only for a documented vineyard nutrition need as a separate localized soil spray at 15 to 30 kg/ha per pass. Do not spray the canopy; Agronomist approval is required.',
    o.exclusion_reason='Not automatic disease control and not a foliar/canopy treatment.',
    o.water_rate_min=NULL,o.water_rate_max=NULL,o.water_rate_unit=NULL,
    o.minimum_rate_per_ha=15,o.maximum_rate_per_ha=30,
    o.minimum_rate_per_ha_unit='kg/ha',o.maximum_rate_per_ha_unit='kg/ha',
    o.compatibility_status='conditional',
    o.compatibility_conditions='Use as a separate localized soil-directed spray. Do not mix calcium into or acidify the mother solution, and do not combine automatically with crop-protection products.'
WHERE p.name='TERRAPLUS SOLUB NPK 8-7-6' AND o.crop_scope='vineyard';

UPDATE treatment_product_profiles r JOIN products p ON p.id=r.product_id
SET r.concentrate_form='liquid',r.formulation_code='SC',r.measure_unit='L',
    r.verification_status='verified',r.estate_authorization_status='confirmed',
    r.estate_authorization_confirmed_on='2026-08-20',
    r.mixing_instructions='Shake and dilute in water following the current authorized label. For vineyard use, remain within 170-420 ml/hL and 1.7-4.2 L/ha; do not use during flowering.',
    r.compatibility_notes='Do not combine automatically. Confirm copper limits, the exact products, sequence and crop stage with the Agronomist even where manufacturer material describes general miscibility.',
    r.label_verified_on='2026-08-20',
    r.label_url='https://www.manica.com/wp-content/uploads/2020/01/Catalogo_Manica_Agrofarmaci_2020_web.pdf',
    r.eligible_for_projection=1,
    r.source_summary='Manufacturer directions and the current official registration record support vineyard downy mildew, bacteriosis and anthracnose at 170-420 ml/hL and 1.7-4.2 L/ha, maximum eight applications and 21-day PHI.'
WHERE p.name='OSSICLOR 20 BLU FLOW';

INSERT INTO product_authorized_uses (
  id,estate_id,product_id,crop_scope,target_code,target_name,authorization_status,authorization_expires_on,
  label_verified_on,label_url,min_dose,max_dose,dose_unit,phi_days,max_applications,resistance_group,
  growth_stage_limits,environmental_restrictions,notes,active
)
SELECT UUID(),p.estate_id,p.id,'vineyard','downy_mildew','Downy mildew','authorized','2029-06-30',
  '2026-08-20','https://www.manica.com/wp-content/uploads/2020/01/Catalogo_Manica_Agrofarmaci_2020_web.pdf',
  1.7,4.2,'L/ha',21,8,'M01','Pre-flowering, post-flowering and bunch-closure treatments; do not use during flowering.',
  'Observe the current authorized label, annual copper limits, crop stage, PHI, weather, PPE and local restrictions.',
  'Manufacturer vineyard directions list downy mildew, bacteriosis and anthracnose at 170-420 ml/hL and 1.7-4.2 L/ha, maximum eight applications. Official registry evidence records registration 012723 through 2029-06-30.',1
FROM products p WHERE p.name='OSSICLOR 20 BLU FLOW'
ON DUPLICATE KEY UPDATE authorization_status=VALUES(authorization_status),authorization_expires_on=VALUES(authorization_expires_on),
  label_verified_on=VALUES(label_verified_on),label_url=VALUES(label_url),min_dose=VALUES(min_dose),max_dose=VALUES(max_dose),
  dose_unit=VALUES(dose_unit),phi_days=VALUES(phi_days),max_applications=VALUES(max_applications),
  resistance_group=VALUES(resistance_group),growth_stage_limits=VALUES(growth_stage_limits),
  environmental_restrictions=VALUES(environmental_restrictions),notes=VALUES(notes),active=1;

UPDATE treatment_product_options o JOIN products p ON p.id=o.product_id
SET o.default_decision='candidate',
    o.selection_conditions='Use only for a confirmed vineyard downy-mildew target under the current authorized label; verify crop stage, copper limits, PHI, weather, PPE and Agronomist approval.',
    o.exclusion_reason=NULL,o.minimum_rate_per_ha=1.7,o.maximum_rate_per_ha=4.2,
    o.minimum_rate_per_ha_unit='L/ha',o.maximum_rate_per_ha_unit='L/ha',
    o.compatibility_status='not_verified',
    o.compatibility_conditions='Do not combine automatically. Confirm the exact products, copper limits, current directions and sequence with the Agronomist.'
WHERE p.name='OSSICLOR 20 BLU FLOW' AND o.crop_scope='vineyard';

INSERT INTO treatment_product_evidence
  (id,estate_id,product_id,evidence_type,source_key,source_reference,observed_form,observed_rate,observed_rate_unit,evidence_date,verification_status,notes)
SELECT UUID(),p.estate_id,p.id,'manufacturer_label',x.source_key,x.source_reference,x.observed_form,x.observed_rate,x.observed_rate_unit,'2026-08-20','verified',x.notes
FROM products p JOIN (
  SELECT 'FRONTIERE' product_name,'manufacturer-directions:frontiere-2.0:2026-08-20' source_key,
    'https://news.kalosgate.com/hubfs/Catalogo%20Prodotti%20KEA/induttori/Copia%20di%20Locandina%20FRONTIERE%202.0_ALTA.pdf' source_reference,
    'liquid' observed_form,.75 observed_rate,'L/ha' observed_rate_unit,
    'K&A manufacturer directions: fruit crops, olive and vineyard foliar use 0.75-1.00 L/ha from vegetative awakening through the crop cycle.' notes UNION ALL
  SELECT 'FERTICUS 18 M','manufacturer-directions:ferticus-18-m:2026-08-20',
    'https://www.manica.com/pdf/area-download/catalogomanica.pdf','wettable powder',300,'g/100 L',
    'Manica manufacturer catalogue: vineyard foliar fertilizer rate 300-500 g/hL; copper 18%, manganese 0.5%; wettable powder.' UNION ALL
  SELECT 'TERRAPLUS SOLUB NPK 8-7-6','manufacturer-directions:terraplus-solub-npk-vineyard:2026-08-20',
    'https://www.compo-expert.com/sites/default/files/2022-09/TerraPlus%20Solub%20NPK_VIGNE_%28pc%29_France.pdf','water-soluble powder',15,'kg/ha',
    'COMPO EXPERT vineyard directions: 15-30 kg/ha per pass; usable by localized soil spraying or fertigation. Not a foliar/canopy direction.' UNION ALL
  SELECT 'OSSICLOR 20 BLU FLOW','manufacturer-directions:ossiclor-20-blu-flow:2026-08-20',
    'https://www.manica.com/wp-content/uploads/2020/01/Catalogo_Manica_Agrofarmaci_2020_web.pdf','SC liquid',1.7,'L/ha',
    'Manica vineyard directions: downy mildew, bacteriosis and anthracnose, 170-420 ml/hL and 1.7-4.2 L/ha, maximum eight applications, 21-day PHI for other crops including vineyard.'
) x ON x.product_name=p.name
ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),observed_form=VALUES(observed_form),
  observed_rate=VALUES(observed_rate),observed_rate_unit=VALUES(observed_rate_unit),evidence_date=VALUES(evidence_date),
  verification_status='verified',notes=VALUES(notes);
