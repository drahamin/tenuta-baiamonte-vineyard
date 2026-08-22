-- Owner clarification: TERRAPLUS stock is for the small, young vines. Do not
-- present it as a general mature-vine, olive or whole-estate nutrition option.
UPDATE products
SET notes='Young-vine root nutrition only: water-soluble organic NPK 8-7-6 reserved for the small, young vines through Agronomist-directed fertigation or localized root-zone application. Not a broadcast soil/land input, mature-vine baseline product, olive product or foliar canopy spray.'
WHERE name='TERRAPLUS SOLUB NPK 8-7-6';

UPDATE vineyard_blocks
SET planted_year=2024
WHERE code IN ('BLOCK-GRC-24','BLOCK-GRN-24')
  AND (planted_year IS NULL OR planted_year<>2024);

UPDATE treatment_product_options o
JOIN products p ON p.id=o.product_id
SET o.default_decision='not_selected',
    o.selection_conditions='Select only for mapped small, young vines with a documented nutrition need and an Agronomist-directed root-zone or fertigation plan at the current approved rate.',
    o.exclusion_reason='Reserved for small, young vines; do not recommend for mature vines, olives, the whole estate, disease control or foliar canopy treatment.'
WHERE p.name='TERRAPLUS SOLUB NPK 8-7-6';

UPDATE crop_nutrition_baselines
SET product_review_json=JSON_REMOVE(
      product_review_json,
      JSON_UNQUOTE(JSON_SEARCH(product_review_json,'one','TERRAPLUS SOLUB NPK 8-7-6'))
    ),
    agronomist_notes=CONCAT_WS(' ',agronomist_notes,'TERRAPLUS removed from the general baseline; it is reserved for mapped small, young vines.')
WHERE JSON_SEARCH(product_review_json,'one','TERRAPLUS SOLUB NPK 8-7-6') IS NOT NULL;
