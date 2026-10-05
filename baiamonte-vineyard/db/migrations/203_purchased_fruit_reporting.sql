-- Distinguish estate harvest from purchased fruit without removing purchased
-- fruit from production, cellar, vintage, or display totals. Purchased fruit
-- is always excluded from estate yield/completion and parcel performance.

ALTER TABLE harvest_lots
  ADD COLUMN IF NOT EXISTS source_type ENUM('estate_harvest','purchased') NOT NULL DEFAULT 'estate_harvest' AFTER lot_code;
ALTER TABLE harvest_lots
  ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(190) NULL AFTER source_type;
ALTER TABLE harvest_lots
  ADD COLUMN IF NOT EXISTS source_plot_reference VARCHAR(190) NULL AFTER supplier_name;

UPDATE harvest_lots
SET source_type='purchased',supplier_name='Steph Yim',source_plot_reference='1200 plot'
WHERE id='20200000-0000-4000-8000-000000000003' OR lot_code='2026-GRN-PUR-01';

-- The vintage series represents all fruit handled for Baiamonte production.
-- Preserve the estate/purchased split in the evidence text and do not invent a
-- crate count for purchased loose fruit.
UPDATE vintage_summaries vs
JOIN seasons s ON s.estate_id=vs.estate_id AND s.vintage_year=vs.vintage_year
SET vs.grapes_kg=(
      SELECT SUM(h.weight_kg) FROM harvest_lots h
      JOIN grape_varieties v ON v.id=h.variety_id
      WHERE h.season_id=s.id AND LOWER(v.name)='grenache'
    ),
    vs.evidence_status='owner_confirmed_estate_plus_purchased',
    vs.reconciliation_note='2026 Grenache production fruit: 399.25 kg estate-grown harvest plus 1,078.00 kg purchased fruit from the owner-supplied "Steph Yim''s 1200 plot" source wording = 1,477.25 kg total fruit received. The purchased fruit has no crate count and is excluded from estate vineyard yield/completion calculations.'
WHERE vs.vintage_year=2026 AND LOWER(vs.variety_name)='grenache';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-203','classify_purchased_fruit_reporting','harvest_lot','2026-GRN-PUR-01',
       JSON_OBJECT('estate_harvest_kg',4838.38,'purchased_fruit_kg',1078.00,
                   'total_fruit_received_kg',5916.38,'grenache_estate_kg',399.25,
                   'grenache_purchased_kg',1078.00,'grenache_total_received_kg',1477.25,
                   'estate_yield_includes_purchased',FALSE,'production_totals_include_purchased',TRUE)
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-203'
    AND a.action='classify_purchased_fruit_reporting'
);
