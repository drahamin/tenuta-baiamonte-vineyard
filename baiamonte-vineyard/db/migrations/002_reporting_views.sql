CREATE OR REPLACE VIEW v_inventory_balance AS
SELECT p.estate_id, p.id AS product_id, p.name, p.product_type, p.unit,
       COALESCE(SUM(m.quantity_delta), 0) AS quantity_on_hand,
       p.reorder_level,
       CASE WHEN p.reorder_level IS NOT NULL AND COALESCE(SUM(m.quantity_delta),0) <= p.reorder_level THEN 1 ELSE 0 END AS needs_reorder
FROM products p
LEFT JOIN inventory_movements m ON m.product_id = p.id
WHERE p.active = 1
GROUP BY p.estate_id, p.id, p.name, p.product_type, p.unit, p.reorder_level;

CREATE OR REPLACE VIEW v_harvest_summary AS
SELECT h.estate_id, s.vintage_year, h.variety_id, v.name AS variety_name,
       MIN(DATE(h.harvested_at)) AS first_pick_date,
       MAX(DATE(h.harvested_at)) AS last_pick_date,
       SUM(COALESCE(h.weight_kg,0)) AS total_kg,
       SUM(COALESCE(h.crate_count,0)) AS total_crates,
       COUNT(*) AS lot_count,
       AVG(h.brix) AS avg_brix,
       AVG(h.ph) AS avg_ph,
       AVG(h.ta_g_l) AS avg_ta_g_l
FROM harvest_lots h
JOIN seasons s ON s.id = h.season_id
JOIN grape_varieties v ON v.id = h.variety_id
GROUP BY h.estate_id, s.vintage_year, h.variety_id, v.name;

CREATE OR REPLACE VIEW v_open_work AS
SELECT t.estate_id, t.id, t.title, t.category, t.priority, t.status, t.due_date,
       b.code AS block_code, b.name AS block_name,
       DATEDIFF(t.due_date, CURDATE()) AS days_until_due
FROM tasks t
LEFT JOIN vineyard_blocks b ON b.id = t.block_id
WHERE t.status IN ('planned','in_progress');

CREATE OR REPLACE VIEW v_latest_block_phenology AS
SELECT p.*
FROM phenology_observations p
JOIN (
  SELECT block_id, MAX(observed_date) AS max_date
  FROM phenology_observations
  GROUP BY block_id
) latest ON latest.block_id = p.block_id AND latest.max_date = p.observed_date;
