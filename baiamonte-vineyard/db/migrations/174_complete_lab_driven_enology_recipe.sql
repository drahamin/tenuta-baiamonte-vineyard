-- Complete the lab-driven recipe: white clarification, red tannin and
-- tartaric-acid decisions remain visible and update from reviewed reports.
UPDATE enology_product_protocols protocol
JOIN enology_product_catalog product ON product.id=protocol.product_catalog_id
SET protocol.required_lab_analytes='ph,total_acidity,potential_alcohol,anthocyanins,total_polyphenols'
WHERE product.product_class='tannin'
  AND protocol.trigger_code IN ('crusher_or_fermentation','pump_over','first_pump_over');

UPDATE enology_product_protocols
SET required_lab_analytes='ph,total_acidity,potassium,tartaric_acid'
WHERE trigger_code='acidification_bench_trial';
