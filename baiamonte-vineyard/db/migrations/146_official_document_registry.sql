CREATE TABLE IF NOT EXISTS official_documents (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  document_type VARCHAR(80) NOT NULL,
  title VARCHAR(255) NOT NULL,
  issuing_authority VARCHAR(190) NULL,
  reference_number VARCHAR(120) NULL,
  issue_date DATE NULL,
  effective_year SMALLINT UNSIGNED NULL,
  status ENUM('current','reference','historical','superseded','draft') NOT NULL DEFAULT 'current',
  original_filename VARCHAR(255) NOT NULL,
  storage_kind ENUM('bundled','uploaded') NOT NULL DEFAULT 'uploaded',
  stored_path VARCHAR(500) NOT NULL,
  mime_type VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
  file_sha256 CHAR(64) NOT NULL,
  file_size BIGINT UNSIGNED NOT NULL,
  page_count SMALLINT UNSIGNED NULL,
  summary TEXT NULL,
  verified_facts JSON NULL,
  related_scope JSON NULL,
  supersedes_document_id CHAR(36) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_official_document_hash (estate_id,file_sha256),
  KEY ix_official_document_type_date (estate_id,document_type,issue_date),
  CONSTRAINT fk_official_document_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_official_document_supersedes FOREIGN KEY (supersedes_document_id) REFERENCES official_documents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-company-deed-2023',id,'company_formation','Agricultural company formation deed','Notary Ottavio D''Angelo','Repertorio 4.218 / Raccolta 2.949','2023-04-28',2023,'current','ATTO.PDF','bundled','official/2023-04-28-company-formation-deed.pdf','application/pdf','2dcd28e10c15cb7cde5b2799d70d42299eb38cab0ec12e4df1fdfd0c70831041',86497,8,'Formation deed for Azienda Agricola Tenuta Baiamonte S.S.',JSON_OBJECT('formation_date','2023-04-28','legal_form','Societa semplice agricola'),JSON_OBJECT('domains',JSON_ARRAY('company','estate'))
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-company-register-2023',id,'company_register','Company register filing result','Camera di Commercio di Firenze / InfoCamere','T 514218636','2023-05-05',2023,'current','Visura.pdf','bundled','official/2023-05-05-company-register.pdf','application/pdf','c3a813c154bc5ec147c8409496492adea12db8637a76f425df8956b737163b1a',312846,7,'Official company-register extract and protocol result.',JSON_OBJECT('registration_date','2023-05-05','rea','FI-692127','legal_form','Societa semplice'),JSON_OBJECT('domains',JSON_ARRAY('company','estate'))
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-harvest-declaration-2025',id,'harvest_declaration','2025 harvest declaration and grower annex','Italian wine-sector declaration (SIAN/AGEA record)',NULL,NULL,2025,'current','Dichiarazione di Vendemmia_Tenuta Baiamonte_2025+F1.pdf','bundled','official/2025-harvest-declaration.pdf','application/pdf','d27c33959ca1f31a45aa7b4e2f6edc9261d67b050c00352cb3811413d25d347a',382421,11,'Official 2025 grape-delivery declaration: 5,042 kg total.',JSON_OBJECT('total_grapes_kg',5042,'white_grapes_kg',1600,'red_grapes_kg',3442,'alicante_kg',406,'grecanico_kg',1600,'nerello_mascalese_kg',3036),JSON_OBJECT('domains',JSON_ARRAY('harvest','enology'),'vintages',JSON_ARRAY(2025),'varieties',JSON_ARRAY('Alicante','Grecanico','Nerello Mascalese'))
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-vineyard-surfaces-2025',id,'vineyard_register','Authoritative vineyard-surface register · 9,144 m²','Italian vineyard register',NULL,'2025-09-05',2025,'current','Scheda Superfici Vitate_Baiamonte_05_09_2025.pdf','bundled','official/2025-09-05-vineyard-surface-register.pdf','application/pdf','c520cfacbd61a5e07cb05893a722f66a9d0d870f4b151b020848b4b5099132f9',11271,6,'Current authoritative vineyard basis: 9,144 m² across cadastral parcels 76, 77 and 93, confirmed by the estate owner on 4 September 2026.',JSON_OBJECT('official_vineyard_area_m2',9144,'alicante_m2',1626,'grecanico_m2',3093,'nerello_mascalese_m2',4425,'parcel_83_76_m2',1685,'parcel_83_77_m2',93,'parcel_83_93_m2',7366,'owner_confirmed_current_on','2026-09-04'),JSON_OBJECT('domains',JSON_ARRAY('atlas','vineyard'),'parcels',JSON_ARRAY('83/76','83/77','83/93'),'varieties',JSON_ARRAY('Alicante','Grecanico','Nerello Mascalese'))
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope,supersedes_document_id)
SELECT 'official-vineyard-surfaces-2026',id,'vineyard_register','New Italian-system extract · incomplete coverage (5,461 m²)','Italian vineyard register',NULL,'2026-09-04',2026,'reference','schedaVigneti-2.pdf','bundled','official/2026-09-04-vineyard-surface-register.pdf','application/pdf','2838ce3cb6377a29229cc2f5aaeeca60d76b8f184e308da3e2ee61c945a1dcec',6944,4,'Italy’s new registry system currently shows only 5,461 m² because it omits part of the vineyard. This reference extract does not supersede the complete old-system 9,144 m² record, which remains the authoritative current basis until Italy corrects the new system.',JSON_OBJECT('reported_vineyard_area_m2',5461,'source_system','italy_new_system','coverage_status','incomplete_new_system_extract','authoritative_current_area_m2',9144,'authoritative_source_system','italy_old_complete_system','alicante_m2',933,'grecanico_m2',1843,'nerello_mascalese_m2',2685,'parcel_83_76_m2',1685,'parcel_83_77_m2',93,'parcel_83_93_m2',3683,'reconciliation_status','incomplete_not_current'),JSON_OBJECT('domains',JSON_ARRAY('atlas','vineyard'),'parcels',JSON_ARRAY('83/76','83/77','83/93'),'varieties',JSON_ARRAY('Alicante','Grecanico','Nerello Mascalese')),NULL
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope),supersedes_document_id=VALUES(supersedes_document_id);

INSERT INTO official_documents
  (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope)
SELECT 'official-cadastral-record-2026',id,'cadastral_record','Current cadastral property record','Agenzia delle Entrate · Direzione Provinciale di Catania','T166480/2026','2026-09-04',2026,'current','Visura Catastale_04_09_2026.pdf','bundled','official/2026-09-04-cadastral-record.pdf','application/pdf','a52d43e66b02cab27c35a4715de41b2959e2ff976886177cf28ecd4f213419bf',18240,3,'Current cadastral extract for Randazzo sheet 83: six land parcels and two buildings.',JSON_OBJECT('land_area_ha',11.5912,'building_units',2,'building_consistency_m2',81,'parcel_83_30_ha',6.1300,'parcel_83_36_ha',1.4755,'parcel_83_76_ha',0.5720,'parcel_83_77_ha',0.0090,'parcel_83_78_ha',2.4453,'parcel_83_93_ha',0.9594),JSON_OBJECT('domains',JSON_ARRAY('atlas','estate'),'parcels',JSON_ARRAY('83/30','83/36','83/76','83/77','83/78','83/93'),'buildings',JSON_ARRAY('83/94','83/95'))
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),status=VALUES(status),stored_path=VALUES(stored_path),verified_facts=VALUES(verified_facts),related_scope=VALUES(related_scope);

UPDATE cadastral_parcels SET official_vineyard_area_ha=0.1685
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='76';
UPDATE cadastral_parcels SET official_vineyard_area_ha=0.0093
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='77';
UPDATE cadastral_parcels SET official_vineyard_area_ha=0.7366
WHERE estate_id='00000000-0000-4000-8000-000000000001' AND cadastral_sheet='83' AND parcel_number='93';

INSERT INTO evidence_references
  (id,estate_id,evidence_type,external_id,title,source_date,confidence,notes,metadata)
SELECT 'evidence-new-vines-registration',id,'user_confirmation','owner-confirmation-2026-09-04-new-vines','New planting awaiting vineyard-register update','2026-09-04 00:00:00.000000','high',
  'Approximately 3,000 m² of new planting is operationally present but is not yet properly recorded in the official vineyard documents. Do not present it as registered surface until updated documentation arrives.',
  JSON_OBJECT('documented_vineyard_area_ha',0.9144,'pending_new_planting_area_ha',0.3000,'working_total_planted_area_ha',1.2144,'expected_productive_year',2027,'current_production_area_ha',0.9144,'projected_productive_area_ha_2027',1.2144,'area_is_approximate',true,'status','awaiting_official_documentation')
FROM estates WHERE id='00000000-0000-4000-8000-000000000001'
ON DUPLICATE KEY UPDATE title=VALUES(title),source_date=VALUES(source_date),confidence=VALUES(confidence),notes=VALUES(notes),metadata=VALUES(metadata);

INSERT INTO entity_evidence (entity_type,entity_id,evidence_id,relationship)
VALUES ('estate_vineyard_area','00000000-0000-4000-8000-000000000001','evidence-new-vines-registration','pending_documentation')
ON DUPLICATE KEY UPDATE relationship=VALUES(relationship);
