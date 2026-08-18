-- Repair Italian day-first and month-only dates that an older importer stored
-- as January 1 year placeholders. The original cell remains in raw_values.
UPDATE historical_cost_records h
JOIN (
  SELECT id,
    CASE
      WHEN raw_date REGEXP '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2}$' THEN
        CASE
          WHEN CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(raw_date,'/',2),'/',-1) AS UNSIGNED) > 12
            THEN STR_TO_DATE(raw_date,'%m/%d/%y')
          ELSE STR_TO_DATE(raw_date,'%d/%m/%y')
        END
      WHEN raw_date REGEXP '^[0-9]{1,2}/20[0-9]{2}$'
        THEN STR_TO_DATE(CONCAT('01/',raw_date),'%d/%m/%Y')
      ELSE NULL
    END parsed_date,
    CASE
      WHEN raw_date REGEXP '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2}$' THEN 'day'
      WHEN raw_date REGEXP '^[0-9]{1,2}/20[0-9]{2}$' THEN 'month'
      ELSE NULL
    END parsed_precision
  FROM (
    SELECT id,JSON_UNQUOTE(JSON_EXTRACT(raw_values,'$[3]')) raw_date
    FROM historical_cost_records
    WHERE source_file_id='1hBQy5GUNw1yoSOod944tr42tm1WruLHvE8Wpdok2WnM'
      AND date_precision='year'
  ) source_dates
) repaired ON repaired.id=h.id
SET h.record_date=repaired.parsed_date,
    h.record_year=YEAR(repaired.parsed_date),
    h.date_precision=repaired.parsed_precision
WHERE repaired.parsed_date IS NOT NULL;
