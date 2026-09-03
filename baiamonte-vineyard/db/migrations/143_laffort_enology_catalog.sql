CREATE TABLE IF NOT EXISTS enology_product_catalog (
  id CHAR(36) PRIMARY KEY,
  manufacturer VARCHAR(120) NOT NULL,
  product_name VARCHAR(220) NOT NULL,
  normalized_name VARCHAR(220) NOT NULL,
  range_code VARCHAR(80) NOT NULL,
  range_name VARCHAR(120) NOT NULL,
  product_class VARCHAR(60) NOT NULL,
  wine_colors VARCHAR(80) NOT NULL DEFAULT 'any',
  process_stages VARCHAR(255) NULL,
  description TEXT NULL,
  product_url VARCHAR(700) NULL,
  pds_url VARCHAR(700) NULL,
  sds_url VARCHAR(700) NULL,
  dose_min DECIMAL(12,4) NULL,
  dose_max DECIMAL(12,4) NULL,
  dose_unit VARCHAR(40) NULL,
  dose_basis VARCHAR(255) NULL,
  dose_verified TINYINT(1) NOT NULL DEFAULT 0,
  source_url VARCHAR(700) NOT NULL,
  source_checked_at DATETIME(6) NULL,
  present_in_latest TINYINT(1) NOT NULL DEFAULT 1,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_product_identity (manufacturer,normalized_name),
  KEY ix_enology_product_use (manufacturer,product_class,range_code,present_in_latest)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enology_product_catalog_sync_runs (
  id CHAR(36) PRIMARY KEY,
  status ENUM('running','processed','partial','failed') NOT NULL,
  source_url VARCHAR(700) NOT NULL,
  source_rows INT NOT NULL DEFAULT 0,
  imported_rows INT NOT NULL DEFAULT 0,
  failed_ranges INT NOT NULL DEFAULT 0,
  error_text TEXT NULL,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  completed_at DATETIME(6) NULL,
  KEY ix_enology_catalog_sync_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE enology_additive_catalog ADD COLUMN product_catalog_id CHAR(36) NULL AFTER estate_id;
ALTER TABLE enology_additive_catalog ADD KEY ix_enology_additive_product (product_catalog_id);
ALTER TABLE enology_additive_catalog ADD CONSTRAINT fk_enology_additive_product FOREIGN KEY (product_catalog_id) REFERENCES enology_product_catalog(id) ON DELETE SET NULL;

INSERT IGNORE INTO enology_product_catalog
  (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,present_in_latest)
VALUES
  (UUID(),'LAFFORT','ZYMAFLORE™ ALPHA','zymaflore alpha','zymaflore','Yeast','yeast','any','inoculation','Torulaspora delbrueckii used with S. cerevisiae for wines with high organoleptic complexity.','https://laffort.com/en/products/zymaflore-alpha/','https://laffort.com/wp-content/uploads/FP/FP_EN_Zymaflore_Alpha.pdf',30,30,'g/hL','Dry-wine sequential inoculation; follow with 20 g/hL approved S. cerevisiae after 24–72 hours.',1,'https://laffort.com/en/ranges/zymaflore-yeast/',1),
  (UUID(),'LAFFORT','ZYMAFLORE™ F83','zymaflore f83','zymaflore','Yeast','yeast','red','inoculation','Yeast for Mediterranean red grape varieties including Grenache.','https://laffort.com/en/products/zymaflore-f83/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/zymaflore-yeast/',1),
  (UUID(),'LAFFORT','ZYMAFLORE™ RX60','zymaflore rx60','zymaflore','Yeast','yeast','red','inoculation','Yeast for fruity and spicy red wines including Grenache.','https://laffort.com/en/products/zymaflore-rx60/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/zymaflore-yeast/',1),
  (UUID(),'LAFFORT','ZYMAFLORE™ X16','zymaflore x16','zymaflore','Yeast','yeast','white,rose','inoculation','Yeast for aromatic white and rosé wines with high production of fermentation aromas.','https://laffort.com/en/products/zymaflore-x16/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/zymaflore-yeast/',1),
  (UUID(),'LAFFORT','ZYMAFLORE™ XORIGIN','zymaflore xorigin','zymaflore','Yeast','yeast','white','inoculation','Yeast for balanced fine white wines that respect grape and terroir character.','https://laffort.com/en/products/zymaflore-xorigin/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/zymaflore-yeast/',1),
  (UUID(),'LAFFORT','LAFAZYM™ PRESS','lafazym press','enzymes','Enzymes','enzyme','white,rose','pressing','Purified pectolytic enzyme for white and rosé pressing and aroma-precursor extraction.','https://laffort.com/en/products/lafazym-press/','https://laffort.com/wp-content/uploads/FP/FP_EN_Lafazym_Press.pdf',2,5,'g/100kg','Adjust for grape skin quality, maturity and sanitation; use as early as possible before pressing.',1,'https://laffort.com/en/ranges/enzyme/',1),
  (UUID(),'LAFFORT','LAFASE™ HE GRAND CRU','lafase he grand cru','enzymes','Enzymes','enzyme','red','maceration,fermentation','Purified pectolytic enzyme for full-bodied red wines rich in colour and structured tannins.','https://laffort.com/en/products/lafase-he-grand-cru/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/enzyme/',1),
  (UUID(),'LAFFORT','NUTRISTART® THIOLS','nutristart thiols','nutrients','Nutrients','nutrient','white,rose','pre-fermentation,fermentation','Complex organic and mineral nutrient designed to support varietal thiol expression.','https://laffort.com/en/products/nutristart-thiols/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/nutrients/',1),
  (UUID(),'LAFFORT','TANIN VR COLOR™','tanin vr color','tannins','Tannins','tannin','red','crushing,maceration','Winemaking tannin candidate for colour-management review.','https://laffort.com/en/products/tanin-vr-color/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/tannins/',1),
  (UUID(),'LAFFORT','TANIN VR SUPRA™','tanin vr supra','tannins','Tannins','tannin','red','fermentation','Winemaking tannin candidate for red-wine fermentation review.','https://laffort.com/en/products/tanin-vr-supra/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/tannins/',1),
  (UUID(),'LAFFORT','OENOFEEL™','oenofeel','yeast_derivatives','Yeast derivatives','yeast_derivative','any','aging','Inactivated yeasts rich in mannoproteins for mouthfeel review.','https://laffort.com/en/products/oenofeel/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/yeast-derivatives/',1),
  (UUID(),'LAFFORT','LACTIC ACID','lactic acid','specific_treatment','Specific treatments','treatment','any','must,fermentation,aging','L(+) natural acid for acidification of musts, fermenting wines and wines.','https://laffort.com/en/products/acide-lactique/',NULL,NULL,NULL,NULL,NULL,0,'https://laffort.com/en/ranges/specific-treatment/',1);

UPDATE enology_additive_catalog a
JOIN enology_product_catalog p ON p.manufacturer='LAFFORT' AND p.normalized_name='zymaflore alpha'
SET a.product_catalog_id=p.id,a.name='ZYMAFLORE™ ALPHA',a.source_reference=CONCAT(a.source_reference,' · official LAFFORT product identity')
WHERE a.name='Zymaflor Alpha';
