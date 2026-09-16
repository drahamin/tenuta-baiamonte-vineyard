-- Complete the digital cellar label with the particulars used by the host
-- winery's paper cards and the fields listed by DM 13 August 2012, art. 17.
-- Keep the product owner and the physical processing establishment separate:
-- the 2026 wines belong to Tenuta Baiamonte and are held/processed at Raiti
-- Emanuela in Linguaglossa under conto lavorazione.
ALTER TABLE wine_lot_legal_profiles
  ADD COLUMN IF NOT EXISTS processing_establishment_name VARCHAR(190) NULL AFTER cantiniere,
  ADD COLUMN IF NOT EXISTS processing_establishment_address VARCHAR(255) NULL AFTER processing_establishment_name,
  ADD COLUMN IF NOT EXISTS custody_basis VARCHAR(120) NULL AFTER processing_establishment_address,
  ADD COLUMN IF NOT EXISTS responsible_operator VARCHAR(190) NULL AFTER custody_basis,
  ADD COLUMN IF NOT EXISTS product_category VARCHAR(190) NULL AFTER wine_color,
  ADD COLUMN IF NOT EXISTS product_category_code VARCHAR(40) NULL AFTER product_category,
  ADD COLUMN IF NOT EXISTS sugar_content_term VARCHAR(120) NULL AFTER denomination,
  ADD COLUMN IF NOT EXISTS production_method VARCHAR(190) NULL AFTER sugar_content_term,
  ADD COLUMN IF NOT EXISTS traditional_terms VARCHAR(255) NULL AFTER production_method,
  ADD COLUMN IF NOT EXISTS certification_body VARCHAR(160) NULL AFTER traditional_terms,
  ADD COLUMN IF NOT EXISTS certification_number VARCHAR(120) NULL AFTER certification_body,
  ADD COLUMN IF NOT EXISTS certification_date DATE NULL AFTER certification_number;

-- Establish the host-cellar identity for the live 2026 vessels shown in the
-- supplied paper-label evidence. Do not infer a DOC/IGP certificate number or
-- expand uncertain handwritten denomination text.
INSERT INTO wine_lot_legal_profiles (
  id,estate_id,wine_lot_id,legal_company_name,processing_establishment_name,
  processing_establishment_address,custody_basis,responsible_operator,
  wine_type,wine_color,product_category,product_category_code,vintage_year,
  origin_country,content_description,processing_phase,certification_body,
  legal_notes,confirmed_by,confirmed_at
)
SELECT
  UUID(),w.estate_id,w.id,'Azienda Agricola Tenuta Baiamonte S.S.',
  'Raiti Emanuela','Contrada Lavina - Linguaglossa (CT)','Conto lavorazione',
  'David Rahamin','Vino tranquillo',
  CASE WHEN c.code='T-03' THEN 'white' WHEN c.code='M-01' THEN 'red' ELSE NULL END,
  'Vino nuovo ancora in fermentazione','VNF',2026,'Italia',
  COALESCE(NULLIF(w.variety_summary,''),NULLIF(w.name,'')),
  CASE WHEN LOWER(COALESCE(w.stage,'')) IN ('must','fermentation','fermenting','maceration')
       THEN 'Alcoholic fermentation' ELSE NULL END,
  'IRVO',
  'Host-cellar paper label reconciled 2026-09-16. Denomination and certificate fields require documentary confirmation before any DOP/IGP claim.',
  'Owner-supplied host-cellar label evidence',NOW(6)
FROM wine_lots w
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
JOIN cellar_containers c ON c.id=w.current_container_id AND c.estate_id=w.estate_id
WHERE c.code IN ('T-03','M-01') AND c.active=1
ON DUPLICATE KEY UPDATE
  processing_establishment_name=COALESCE(NULLIF(processing_establishment_name,''),VALUES(processing_establishment_name)),
  processing_establishment_address=COALESCE(NULLIF(processing_establishment_address,''),VALUES(processing_establishment_address)),
  custody_basis=COALESCE(NULLIF(custody_basis,''),VALUES(custody_basis)),
  responsible_operator=COALESCE(NULLIF(responsible_operator,''),VALUES(responsible_operator)),
  product_category=COALESCE(NULLIF(product_category,''),VALUES(product_category)),
  product_category_code=COALESCE(NULLIF(product_category_code,''),VALUES(product_category_code)),
  certification_body=COALESCE(NULLIF(certification_body,''),VALUES(certification_body)),
  legal_notes=CONCAT_WS('\n',NULLIF(legal_notes,''),VALUES(legal_notes));
