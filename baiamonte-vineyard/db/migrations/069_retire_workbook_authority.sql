-- Workbooks are retired. Preserve original evidence tables for audit history, but
-- make every operational planning and finance record identify its current
-- authority as the database.

ALTER TABLE production_forecasts ALTER COLUMN source SET DEFAULT 'database planning';
ALTER TABLE grape_allocation_plans ALTER COLUMN source SET DEFAULT 'database planning';
ALTER TABLE wine_output_plans ALTER COLUMN source SET DEFAULT 'database planning';

UPDATE production_forecasts SET source='database planning' WHERE LOWER(source) LIKE '%workbook%';
UPDATE grape_allocation_plans SET source='database planning' WHERE LOWER(source) LIKE '%workbook%';
UPDATE wine_output_plans SET source='database planning' WHERE LOWER(source) LIKE '%workbook%';

UPDATE finance_parties SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE financial_documents SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE cash_transactions SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE inventory_snapshots SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE price_entries SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE financial_scenarios SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE forecast_assumptions SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE annual_financial_summary SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE monthly_financial_summary SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';
UPDATE contract_service_costs SET source='database migrated record' WHERE LOWER(source) LIKE '%workbook%';

UPDATE olive_records SET status='historical database actual' WHERE LOWER(COALESCE(status,'')) LIKE '%workbook%';

UPDATE data_authority_domains
SET system_of_record='MariaDB',
    migration_source='Frozen historical evidence already stored in MariaDB',
    notes=CONCAT_WS(' ',NULLIF(notes,''),'Workbook ingestion is permanently retired; authenticated database records and connected authoritative services are the only update paths.')
WHERE estate_id='00000000-0000-4000-8000-000000000001';
