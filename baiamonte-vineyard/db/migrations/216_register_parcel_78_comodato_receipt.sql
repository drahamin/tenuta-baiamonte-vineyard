INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-parcel-78-comodato-2026',id,'contract','Registered comodato for Randazzo parcel 83/78','Agenzia delle Entrate - Ufficio territoriale di Catania','002876 - serie 3X / protocollo 26100609245919455-000001','2026-10-06',2026,'current',
       'ricevuta registrazione particella 78.pdf','bundled','official/2026-10-06-parcel-83-78-loan-registration.pdf','application/pdf',
       '70c3627631d000b06406bf56dc87b74419eaed29cf497d743e4381c1f38ba90f',17824,3,
       'Agenzia delle Entrate receipt confirming registration of the real-property comodato for Randazzo land parcel sheet 83, parcel 78.',
       JSON_OBJECT('registration_date','2026-10-06','registration_number','002876','series','3X','receipt_protocol','26100609245919455-000001','contract_date','2026-01-02','tenure_start','2026-01-02','tenure_end','2046-12-31','municipality','Randazzo','municipality_code','H175','cadastre','TERRENI','cadastral_sheet','83','parcel_number','78'),
       JSON_OBJECT('domains',JSON_ARRAY('atlas','estate','contracts'),'parcels',JSON_ARRAY('83/78'))
FROM estates
WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE
  title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

UPDATE cadastral_parcels
SET tenure='Comodato',
    contract_protocol='AdE 002876 serie 3X / 26100609245919455-000001',
    tenure_start='2026-01-02',
    tenure_end='2046-12-31',
    notes='Official land parcel from cadastral record T166480/2026; registered comodato receipt dated 2026-10-06; verified map boundary still required'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND cadastral_sheet='83'
  AND parcel_number='78';
