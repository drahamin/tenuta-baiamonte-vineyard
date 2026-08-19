UPDATE data_authority_domains
SET migration_source='Frozen historical migration evidence in MariaDB',
    notes=CONCAT_WS(' ', NULLIF(notes,''), 'As of release 1.3.9, workbooks are not read, synchronized or accepted by the running application.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND migration_source IS NOT NULL;
