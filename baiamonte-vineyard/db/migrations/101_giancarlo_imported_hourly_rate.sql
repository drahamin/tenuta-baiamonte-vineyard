-- Owner-authoritative correction 2026-08-21:
-- Giancarlo's imported attendance hours are valued at EUR 10 per hour.
-- Service/expense-only rows remain untouched because they are not hourly labor.
UPDATE labor_entries
SET hourly_rate_eur=10.00,
    labor_cost_eur=ROUND((COALESCE(regular_hours,0)+COALESCE(overtime_hours,0))*10.00,2),
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[OWNER AUTHORITATIVE 2026-08-21] Imported Giancarlo attendance is valued at EUR 10/hour.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND LOWER(person_or_crew) LIKE 'giancarlo%'
  AND COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)>0
  AND (entry_source IS NULL OR entry_source IN ('historical_import','monthly_total','workbook_import'));
