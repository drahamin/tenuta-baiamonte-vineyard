-- Annual vineyard soil evidence and Agronomist-reviewed fertilization outlook.
-- Laboratory source files remain in intake_items; values here are structured
-- evidence and never constitute an automatic fertilizer application order.
CREATE TABLE IF NOT EXISTS vineyard_soil_samples (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  intake_item_id CHAR(36) NULL,
  sampled_on DATE NOT NULL,
  laboratory VARCHAR(190) NULL,
  sample_scope VARCHAR(190) NOT NULL DEFAULT 'Whole vineyard',
  ph DECIMAL(6,3) NULL,
  organic_matter_pct DECIMAL(8,3) NULL,
  nitrogen_g_kg DECIMAL(10,3) NULL,
  phosphorus_mg_kg DECIMAL(10,3) NULL,
  potassium_mg_kg DECIMAL(10,3) NULL,
  ec_ds_m DECIMAL(10,4) NULL,
  source_status ENUM('values_entered','analysis_pending','review_required','reviewed') NOT NULL DEFAULT 'analysis_pending',
  notes TEXT NULL,
  recorded_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_soil_sample_year (estate_id,season_id,sampled_on),
  CONSTRAINT fk_soil_sample_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_soil_sample_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE RESTRICT,
  CONSTRAINT fk_soil_sample_intake FOREIGN KEY (intake_item_id) REFERENCES intake_items(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vineyard_fertilization_reviews (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  review_status ENUM('draft','approved','rejected') NOT NULL DEFAULT 'draft',
  agronomist_notes TEXT NULL,
  reviewed_by VARCHAR(190) NULL,
  reviewed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_fertilization_review_year (estate_id,season_id),
  CONSTRAINT fk_fertilization_review_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_fertilization_review_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vineyard_fertilizer_applications (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  product_id CHAR(36) NOT NULL,
  application_date DATE NOT NULL,
  quantity DECIMAL(12,3) NOT NULL,
  unit VARCHAR(30) NOT NULL,
  application_scope VARCHAR(190) NOT NULL,
  evidence_status ENUM('planned','owner_confirmed','verified') NOT NULL DEFAULT 'owner_confirmed',
  notes TEXT NULL,
  recorded_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_fertilizer_application (estate_id,product_id,application_date,application_scope),
  CONSTRAINT fk_fertilizer_application_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_fertilizer_application_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fertilizer_application_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Product identity is seeded so the owner-confirmed application can post even
-- before Fatture in Cloud supplies the authoritative purchase line.
INSERT INTO products (id,estate_id,name,product_type,unit,supplier,notes,active)
SELECT UUID(),e.id,'NOVATEC CLASSIC 12-8-16','fertilizer','kg','AGRIPLANET S.R.L.',
  'Granular fertilizer. Purchase evidence is not proof of field application; exact scope, timing and applied quantity require a field record.',1
FROM estates e WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE product_type='fertilizer',unit='kg',supplier='AGRIPLANET S.R.L.',active=1;

INSERT INTO vineyard_fertilizer_applications
  (id,estate_id,season_id,product_id,application_date,quantity,unit,application_scope,evidence_status,notes,recorded_by)
SELECT '20260305-0429-0000-8000-000000000001',e.id,s.id,p.id,'2026-03-05',500,'kg','Whole vineyard','owner_confirmed',
  'Owner authoritative confirmation: all 500 kg purchased on invoice 429 was applied to the whole vineyard on March 5, 2026. Exact distribution method and operator were not separately supplied.',
  'owner confirmation'
FROM estates e JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN products p ON p.estate_id=e.id AND p.name='NOVATEC CLASSIC 12-8-16'
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE quantity=500,unit='kg',evidence_status='owner_confirmed',notes=VALUES(notes),recorded_by='owner confirmation';

INSERT INTO inventory_movements
  (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes)
SELECT '20260305-0429-1000-8000-000000000001',a.estate_id,a.product_id,'2026-03-05 12:00:00','use',-500,'fertilizer_application',a.id,
  'Owner-confirmed application of all 500 kg NOVATEC CLASSIC 12-8-16 to the whole vineyard on 2026-03-05.'
FROM vineyard_fertilizer_applications a
WHERE a.id='20260305-0429-0000-8000-000000000001'
  AND NOT EXISTS (SELECT 1 FROM inventory_movements m WHERE m.reference_type='fertilizer_application' AND m.reference_id=a.id);
