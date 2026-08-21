-- Owner planning default: finished bottles are valued at EUR 12 each until edited.
UPDATE inventory_snapshots s
JOIN products p ON p.id=s.product_id AND p.estate_id=s.estate_id
SET s.average_sales_price=12.00,
    s.inventory_value=ROUND(COALESCE(s.quantity_on_hand,0)*12.00,2)
WHERE LOWER(TRIM(p.unit))='bt.'
  AND (s.average_sales_price IS NULL OR s.average_sales_price=0)
  AND (s.inventory_value IS NULL OR s.inventory_value=0);
