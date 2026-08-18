ALTER TABLE historical_cost_records
  ADD COLUMN IF NOT EXISTS labor_hours DECIMAL(10,2) NULL AFTER amount_eur;

UPDATE historical_cost_records
SET labor_hours=CAST(REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(LOWER(description),' ore',1),' ',-1),',','.') AS DECIMAL(10,2))
WHERE labor_hours IS NULL
  AND LOWER(description) REGEXP '[0-9]+([,.][0-9]+)?[[:space:]]+ore';
