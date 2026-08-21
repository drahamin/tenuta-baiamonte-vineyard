-- The live January-June imports use entry_source='manual' but retain a stable
-- HISTORICAL-GIANCARLO source id. Apply the owner-confirmed EUR 10/hour rate
-- only to those hourly rows; expense/service rows are intentionally excluded.
UPDATE labor_entries
SET hourly_rate_eur=10.00,
    labor_cost_eur=ROUND((COALESCE(regular_hours,0)+COALESCE(overtime_hours,0))*10.00,2),
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[OWNER AUTHORITATIVE 2026-08-21] Imported Giancarlo attendance is valued at EUR 10/hour.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_labor_id LIKE 'HISTORICAL-GIANCARLO-%-MONTHLY'
  AND COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)>0;
