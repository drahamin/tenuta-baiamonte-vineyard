-- Bottling closes the grape-to-wine production cycle. A completed run snapshots
-- every source tank, wine lot and legal parcel before clearing the vessels and
-- posting the finished bottles to vintage inventory.
CREATE TABLE IF NOT EXISTS bottling_runs (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  run_code VARCHAR(100) NOT NULL,
  bottled_at DATETIME(6) NOT NULL,
  wine_name VARCHAR(180) NOT NULL,
  legal_lot_code VARCHAR(100) NOT NULL,
  denomination VARCHAR(180) NULL,
  origin_country VARCHAR(100) NOT NULL DEFAULT 'Italia',
  alcohol_pct DECIMAL(6,3) NULL,
  bottle_size_ml SMALLINT UNSIGNED NOT NULL DEFAULT 750,
  bottles_produced INT UNSIGNED NOT NULL,
  bottled_volume_l DECIMAL(12,3) NOT NULL,
  source_volume_l DECIMAL(12,3) NOT NULL,
  process_loss_l DECIMAL(12,3) NOT NULL DEFAULT 0,
  bottles_per_case SMALLINT UNSIGNED NULL,
  cases_produced INT UNSIGNED NULL,
  status ENUM('planned','completed','void') NOT NULL DEFAULT 'completed',
  legal_review_status ENUM('draft','review_required','approved') NOT NULL DEFAULT 'review_required',
  recorded_by VARCHAR(190) NULL,
  notes TEXT NULL,
  completed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_bottling_run_code (estate_id,season_id,run_code),
  UNIQUE KEY uq_bottling_legal_lot (estate_id,legal_lot_code),
  KEY ix_bottling_vintage_date (estate_id,season_id,bottled_at),
  CONSTRAINT fk_bottling_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bottling_run_sources (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  bottling_run_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  container_id CHAR(36) NOT NULL,
  drained_volume_l DECIMAL(12,3) NOT NULL,
  wine_lot_code_snapshot VARCHAR(80) NOT NULL,
  wine_lot_name_snapshot VARCHAR(160) NOT NULL,
  variety_snapshot VARCHAR(255) NULL,
  container_code_snapshot VARCHAR(60) NOT NULL,
  container_name_snapshot VARCHAR(160) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_bottling_source_lot (bottling_run_id,wine_lot_id),
  KEY ix_bottling_source_container (estate_id,container_id),
  CONSTRAINT fk_bottling_source_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_source_run FOREIGN KEY (bottling_run_id) REFERENCES bottling_runs(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_source_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_bottling_source_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bottling_run_parcels (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  bottling_run_id CHAR(36) NOT NULL,
  parcel_id CHAR(36) NULL,
  municipality_snapshot VARCHAR(120) NOT NULL,
  cadastral_sheet_snapshot VARCHAR(40) NOT NULL,
  parcel_number_snapshot VARCHAR(40) NOT NULL,
  source_harvest_lots INT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_bottling_parcel_snapshot (bottling_run_id,municipality_snapshot,cadastral_sheet_snapshot,parcel_number_snapshot),
  CONSTRAINT fk_bottling_parcel_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_parcel_run FOREIGN KEY (bottling_run_id) REFERENCES bottling_runs(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_parcel FOREIGN KEY (parcel_id) REFERENCES cadastral_parcels(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finished_wine_lots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  bottling_run_id CHAR(36) NULL,
  legal_lot_code VARCHAR(100) NOT NULL,
  wine_name VARCHAR(180) NOT NULL,
  bottle_size_ml SMALLINT UNSIGNED NOT NULL DEFAULT 750,
  initial_bottles INT UNSIGNED NOT NULL,
  status ENUM('in_stock','depleted','held','archived') NOT NULL DEFAULT 'in_stock',
  legal_data_json JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_finished_wine_lot (estate_id,legal_lot_code),
  CONSTRAINT fk_finished_wine_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_finished_wine_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE RESTRICT,
  CONSTRAINT fk_finished_wine_bottling FOREIGN KEY (bottling_run_id) REFERENCES bottling_runs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finished_wine_inventory_movements (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  finished_wine_lot_id CHAR(36) NOT NULL,
  movement_at DATETIME(6) NOT NULL,
  movement_type ENUM('bottled','sale','hospitality','sample','damage','adjustment','return') NOT NULL,
  bottle_delta INT NOT NULL,
  reference_type VARCHAR(60) NULL,
  reference_id CHAR(36) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_finished_inventory_lot_date (finished_wine_lot_id,movement_at),
  CONSTRAINT fk_finished_inventory_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_finished_inventory_lot FOREIGN KEY (finished_wine_lot_id) REFERENCES finished_wine_lots(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bottling_cost_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  cost_category ENUM('bottle','cork','front_label','back_label','capsule','case') NOT NULL,
  product_id CHAR(36) NULL,
  cost_per_unit_eur DECIMAL(14,6) NOT NULL,
  units_per_bottle DECIMAL(12,6) NOT NULL DEFAULT 1,
  fixed_cost_eur DECIMAL(14,2) NOT NULL DEFAULT 0,
  supplier VARCHAR(180) NULL,
  source_kind ENUM('fattureincloud','invoice','delivery_note','order','quote','manual','prior_year') NOT NULL DEFAULT 'manual',
  source_document_number VARCHAR(120) NULL,
  source_document_date DATE NULL,
  source_financial_document_id CHAR(36) NULL,
  notes TEXT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_bottling_cost_category (estate_id,vintage_year,cost_category),
  CONSTRAINT fk_bottling_cost_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_cost_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
  CONSTRAINT fk_bottling_cost_document FOREIGN KEY (source_financial_document_id) REFERENCES financial_documents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bottling_packaging_usage (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  bottling_run_id CHAR(36) NOT NULL,
  cost_category ENUM('bottle','cork','front_label','back_label','capsule','case') NOT NULL,
  product_id CHAR(36) NULL,
  quantity_used DECIMAL(14,3) NOT NULL,
  unit_cost_eur DECIMAL(14,6) NULL,
  total_cost_eur DECIMAL(14,2) NULL,
  cost_source_snapshot VARCHAR(500) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_bottling_usage_category (bottling_run_id,cost_category),
  CONSTRAINT fk_bottling_usage_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_usage_run FOREIGN KEY (bottling_run_id) REFERENCES bottling_runs(id) ON DELETE CASCADE,
  CONSTRAINT fk_bottling_usage_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_bottling_summaries (
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  grapes_kg DECIMAL(12,3) NULL,
  wine_l DECIMAL(12,3) NOT NULL,
  bottle_equivalents_750ml INT UNSIGNED NOT NULL,
  completion_status ENUM('equivalent_only','bottled_complete','review_required') NOT NULL DEFAULT 'equivalent_only',
  evidence_note TEXT NULL,
  PRIMARY KEY (estate_id,vintage_year),
  CONSTRAINT fk_historical_bottling_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE vintage_summaries ADD COLUMN IF NOT EXISTS bottle_equivalents_750ml INT UNSIGNED NULL AFTER wine_l;

INSERT INTO products (id,estate_id,name,product_type,unit,supplier,notes,active)
SELECT UUID(),e.id,x.name,'packaging','each',x.supplier,x.notes,1
FROM estates e JOIN (
  SELECT 'Bottling glass bottle 750 ml' name,'Mediterranea Vetri' supplier,'Borg. Virgo 750 ml glass bottle; current cost comes from Fatture in Cloud when a newer matched line exists.' notes UNION ALL
  SELECT 'Natural cork 44x24 mm','Parramon Exportap','Fleur Miroir natural cork; current cost comes from Fatture in Cloud when a newer matched line exists.' UNION ALL
  SELECT 'Front wine label','WeLabel / Umbra Label','Front label, shared generic packaging SKU; variety-specific artwork remains in the source document.' UNION ALL
  SELECT 'Back wine label','WeLabel / Umbra Label','Back label, shared generic packaging SKU; vintage and variety artwork remain in the source document.' UNION ALL
  SELECT 'Polylaminate bottle capsule','Intercap','29.30x55 mm decorated polylaminate closure/capsule.' UNION ALL
  SELECT 'Six-bottle case box','SCIA Packaging','Printed 305x260x175 case box. Six bottles per case is an editable planning assumption until the physical case is confirmed.'
) x
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE product_type='packaging',unit='each',supplier=VALUES(supplier),notes=VALUES(notes),active=1;

INSERT INTO bottling_cost_profiles
  (id,estate_id,vintage_year,cost_category,product_id,cost_per_unit_eur,units_per_bottle,fixed_cost_eur,supplier,source_kind,source_document_number,source_document_date,notes,updated_by)
SELECT UUID(),e.id,x.vintage_year,x.cost_category,p.id,x.unit_cost,x.units_per_bottle,x.fixed_cost,x.supplier,x.source_kind,x.document_number,x.document_date,x.notes,'migration-097'
FROM estates e JOIN (
  SELECT 2025 vintage_year,'bottle' cost_category,'Bottling glass bottle 750 ml' product_name,0.365000 unit_cost,1.000000 units_per_bottle,355.51 fixed_cost,'Mediterranea Vetri' supplier,'delivery_note' source_kind,'147' document_number,'2025-03-05' document_date,'3,696 bottles. Fixed cost retains pallets, interlayers, glass contribution and transport; verify against the posted Fatture record before final costing.' notes UNION ALL
  SELECT 2025,'cork','Natural cork 44x24 mm',0.794000,1.000000,0,'Parramon Exportap','order','30/2530105','2025-02-11','3,000 natural corks at EUR 794 per 1,000; order evidence, replaced automatically when a newer invoiced Fatture line is matched.' UNION ALL
  SELECT 2025,'front_label','Front wine label',0.131370,1.000000,380.00,'WeLabel / Umbra Label','quote','10414-25','2025-03-12','19,000 front labels. Fixed cost includes EUR 300 hot-stamp plate and EUR 80 screen contribution; quote evidence.' UNION ALL
  SELECT 2025,'back_label','Back wine label',0.089570,1.000000,0,'WeLabel / Umbra Label','quote','10414-25','2025-03-12','9,800 back labels; quote evidence.' UNION ALL
  SELECT 2025,'capsule','Polylaminate bottle capsule',0.063700,1.000000,350.00,'Intercap','order','IMC-83560','2025-04-23','12,000 capsules. Fixed cost includes EUR 160 top and EUR 190 side hot-stamp plates; order evidence.' UNION ALL
  SELECT 2026,'case','Six-bottle case box',1.500000,0.166667,393.23,'SCIA Packaging','invoice','553','2026-06-26','1,195 printed cases. Fixed cost includes EUR 295 print setup, EUR 60 transport and EUR 38.23 CONAI; the advance payment is not counted as a second cost.'
) x
JOIN products p ON p.estate_id=e.id AND p.name=x.product_name
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),cost_per_unit_eur=VALUES(cost_per_unit_eur),units_per_bottle=VALUES(units_per_bottle),fixed_cost_eur=VALUES(fixed_cost_eur),supplier=VALUES(supplier),source_kind=VALUES(source_kind),source_document_number=VALUES(source_document_number),source_document_date=VALUES(source_document_date),notes=VALUES(notes);

INSERT INTO historical_bottling_summaries
  (estate_id,vintage_year,grapes_kg,wine_l,bottle_equivalents_750ml,completion_status,evidence_note)
SELECT e.id,x.vintage_year,x.grapes_kg,x.wine_l,x.bottles,'equivalent_only','Owner-authoritative 2026-08-21 vintage total. Bottle equivalents are a 750 ml conversion, not an invented bottling date, SKU split or remaining-stock count.'
FROM estates e JOIN (
  SELECT 2023 vintage_year,5610.000 grapes_kg,3755.000 wine_l,5007 bottles UNION ALL
  SELECT 2024,NULL,2357.000,3143 UNION ALL
  SELECT 2025,5236.000,3998.000,5333
) x WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE grapes_kg=VALUES(grapes_kg),wine_l=VALUES(wine_l),bottle_equivalents_750ml=VALUES(bottle_equivalents_750ml),completion_status='equivalent_only',evidence_note=VALUES(evidence_note);

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,grapes_kg,wine_l,bottle_equivalents_750ml,evidence_status,reconciliation_note)
SELECT e.id,x.vintage_year,'Vintage total',x.grapes_kg,x.wine_l,x.bottles,'owner_authoritative','Authoritative total supplied 2026-08-21. Bottle count is a 750 ml equivalent; 2024 grape kilograms remain unknown.'
FROM estates e JOIN (
  SELECT 2023 vintage_year,5610.000 grapes_kg,3755.000 wine_l,5007 bottles UNION ALL
  SELECT 2024,NULL,2357.000,3143 UNION ALL
  SELECT 2025,5236.000,3998.000,5333
) x WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE grapes_kg=VALUES(grapes_kg),wine_l=VALUES(wine_l),bottle_equivalents_750ml=VALUES(bottle_equivalents_750ml),evidence_status=VALUES(evidence_status),reconciliation_note=VALUES(reconciliation_note);
