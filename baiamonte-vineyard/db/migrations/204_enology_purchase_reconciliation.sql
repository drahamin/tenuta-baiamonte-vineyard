-- Idempotent supplier-to-catalog mapping and purchase ledger for cellar products.
-- Fatture in Cloud remains the source of purchase documents; this table gives
-- enology a durable, auditable bridge from invoice line to product use.
CREATE TABLE IF NOT EXISTS enology_supplier_product_mappings (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  supplier_key VARCHAR(120) NOT NULL,
  supplier_article_code VARCHAR(80) NOT NULL,
  product_catalog_id CHAR(36) NOT NULL,
  package_quantity DECIMAL(12,4) NOT NULL,
  package_unit VARCHAR(20) NOT NULL,
  description_alias VARCHAR(255) NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_supplier_article (estate_id,supplier_key,supplier_article_code),
  CONSTRAINT fk_enology_supplier_mapping_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_supplier_mapping_product FOREIGN KEY (product_catalog_id) REFERENCES enology_product_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enology_product_purchase_lines (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  financial_document_line_id CHAR(36) NOT NULL,
  product_catalog_id CHAR(36) NULL,
  supplier_name VARCHAR(160) NOT NULL,
  supplier_article_code VARCHAR(80) NULL,
  invoice_number VARCHAR(100) NOT NULL,
  invoice_date DATE NOT NULL,
  description VARCHAR(700) NOT NULL,
  package_count DECIMAL(12,4) NOT NULL,
  purchased_quantity DECIMAL(14,4) NULL,
  purchased_unit VARCHAR(20) NULL,
  taxable_amount_eur DECIMAL(14,2) NOT NULL DEFAULT 0,
  match_status ENUM('matched','review') NOT NULL DEFAULT 'review',
  source VARCHAR(40) NOT NULL DEFAULT 'fattureincloud',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_purchase_financial_line (financial_document_line_id),
  KEY ix_enology_purchase_product (estate_id,product_catalog_id,invoice_date),
  CONSTRAINT fk_enology_purchase_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_purchase_financial_line FOREIGN KEY (financial_document_line_id) REFERENCES financial_document_lines(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_purchase_product FOREIGN KEY (product_catalog_id) REFERENCES enology_product_catalog(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO enology_supplier_product_mappings
  (id,estate_id,supplier_key,supplier_article_code,product_catalog_id,package_quantity,package_unit,description_alias)
SELECT UUID(),e.id,'enodoro',x.article_code,p.id,x.package_quantity,'g',x.description_alias
FROM estates e
JOIN (
  SELECT 'EPE919' article_code,'nutriferm advance' product_key,1000 package_quantity,'NUTRIFERM ADVANCE KG.1' description_alias
  UNION ALL SELECT 'EPC852','enartiszym color plus',250,'ENARTIS ZYM COLOR PLUS KG.0,250'
  UNION ALL SELECT 'ENA026','enartisferm q grace',500,'ENARTIS FERM Q GRACE KG 0.500'
  UNION ALL SELECT 'EPE548','enartispro tinto',1000,'ENARTIS PRO TINTO KG.1'
  UNION ALL SELECT 'EPE178','claril af',1000,'CLARIL AF KG.1'
  UNION ALL SELECT 'EPC497','nutriferm arom plus',1000,'NUTRIFERM AROM PLUS KG.1'
  UNION ALL SELECT 'EPC436','enartisferm es181',500,'ENARTIS FERM SELECTION ES181 GR.500'
  UNION ALL SELECT 'EPC399','enartisferm d20',500,'ENARTIS FERM D-20 GR.500'
  UNION ALL SELECT 'EPC843','enartiszym rs p',100,'ENARTIS ZYM RSP GR.100'
  UNION ALL SELECT 'EPE787','enartistan rouge',1000,'ENARTIS TAN ROUGE KG.1 GRANULARE'
  UNION ALL SELECT 'ENA029','enartispro blanco',1000,'ENARTIS PRO BLANCO KG.1 NEW'
) x
JOIN enology_product_catalog p ON p.manufacturer='ENARTIS' AND p.normalized_name=x.product_key
ON DUPLICATE KEY UPDATE product_catalog_id=VALUES(product_catalog_id),package_quantity=VALUES(package_quantity),package_unit=VALUES(package_unit),description_alias=VALUES(description_alias),active=1;
