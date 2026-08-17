ALTER TABLE cellar_containers
  MODIFY COLUMN container_type ENUM('tank','fermenter','aging','barrel','amphora','demijohn','bin','press','other') NOT NULL DEFAULT 'tank';

ALTER TABLE wine_lot_legal_profiles
  ADD COLUMN IF NOT EXISTS legal_company_name VARCHAR(255) NULL AFTER wine_lot_id,
  ADD COLUMN IF NOT EXISTS vat_number VARCHAR(32) NULL AFTER legal_company_name,
  ADD COLUMN IF NOT EXISTS pec VARCHAR(255) NULL AFTER vat_number,
  ADD COLUMN IF NOT EXISTS telephone VARCHAR(64) NULL AFTER pec,
  ADD COLUMN IF NOT EXISTS cantiniere VARCHAR(190) NULL AFTER telephone;

UPDATE wine_lot_legal_profiles
SET legal_company_name=COALESCE(NULLIF(legal_company_name,''),'Azienda Agricola Tenuta Baiamonte'),
    vat_number=COALESCE(NULLIF(vat_number,''),'07276090482'),
    pec=COALESCE(NULLIF(pec,''),'tenutabaiamonte@pec.it'),
    telephone=COALESCE(NULLIF(telephone,''),'+39 3397732042'),
    cantiniere=COALESCE(NULLIF(cantiniere,''),'Sebastiano Vinci');
