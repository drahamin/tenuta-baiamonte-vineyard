-- Finished wine bottles use the owner-set EUR 12 planning value by default.
-- Other bottled products retain their existing unit value while their total is repaired.
UPDATE inventory_snapshots s
JOIN products p ON p.id=s.product_id AND p.estate_id=s.estate_id
SET s.average_sales_price=CASE WHEN LOWER(TRIM(p.category_name))='vino' THEN 12.00 ELSE COALESCE(NULLIF(s.average_sales_price,0),12.00) END,
    s.inventory_value=ROUND(COALESCE(s.quantity_on_hand,0)*CASE WHEN LOWER(TRIM(p.category_name))='vino' THEN 12.00 ELSE COALESCE(NULLIF(s.average_sales_price,0),12.00) END,2)
WHERE LOWER(TRIM(p.unit))='bt.';
