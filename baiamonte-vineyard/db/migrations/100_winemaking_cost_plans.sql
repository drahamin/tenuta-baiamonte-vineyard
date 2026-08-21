CREATE TABLE IF NOT EXISTS winemaking_cost_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT UNSIGNED NOT NULL,
  provider_name VARCHAR(180) NOT NULL,
  planned_cost_eur DECIMAL(14,2) NOT NULL DEFAULT 0,
  status ENUM('planned','invoiced','complete','void') NOT NULL DEFAULT 'planned',
  notes TEXT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_winemaking_cost_year (estate_id,vintage_year),
  CONSTRAINT fk_winemaking_cost_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO winemaking_cost_plans (id,estate_id,vintage_year,provider_name,planned_cost_eur,status,notes,updated_by)
SELECT UUID(),e.id,x.vintage_year,x.provider,x.amount,'planned',x.notes,'owner confirmation'
FROM estates e JOIN (
  SELECT 2025 vintage_year,'GAMBINO SONIA' provider,20026.00 amount,'Annual winemaking service. The Fatture in Cloud invoice is actual financial evidence; this is not glass-bottle packaging.' notes UNION ALL
  SELECT 2026,'Sebastiano Vinci',21000.00,'Owner-confirmed pre-invoice annual winemaking planning amount. Replace the forecast with the actual invoice when it arrives.'
) x WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE provider_name=VALUES(provider_name),planned_cost_eur=VALUES(planned_cost_eur),notes=VALUES(notes);

-- Repair the prior false match that made a Sonia winemaking line look like a bottle purchase.
UPDATE financial_document_lines fdl
JOIN financial_documents fd ON fd.id=fdl.document_id
JOIN finance_parties fp ON fp.id=fd.party_id
JOIN products p ON p.id=fdl.product_id
SET fdl.product_id=NULL
WHERE fd.estate_id='00000000-0000-4000-8000-000000000001'
  AND UPPER(REPLACE(fp.name,' ','')) LIKE '%GAMBINOSONIA%'
  AND p.name='Bottling glass bottle 750 ml';

-- Classify the actual supplier costs in Finance without claiming historical field use.
UPDATE financial_document_lines fdl
JOIN financial_documents fd ON fd.id=fdl.document_id
JOIN finance_parties fp ON fp.id=fd.party_id
JOIN cost_centers cc ON cc.estate_id=fd.estate_id
SET fdl.cost_center_id=cc.id
WHERE fd.estate_id='00000000-0000-4000-8000-000000000001'
  AND ((UPPER(REPLACE(fp.name,' ','')) LIKE '%AGRIPLANET%' AND cc.code='VINEYARD')
    OR (UPPER(REPLACE(fp.name,' ','')) REGEXP 'GAMBINOSONIA|SEBASTIANOVINCI|MEDITERRANEAVETRI|PARRAMON|INTERCAP|SCIA' AND cc.code='CELLAR'));

UPDATE financial_document_lines fdl
JOIN financial_documents fd ON fd.id=fdl.document_id
JOIN seasons s ON s.estate_id=fd.estate_id AND s.vintage_year=YEAR(fd.document_date)
SET fdl.season_id=s.id
WHERE fd.estate_id='00000000-0000-4000-8000-000000000001'
  AND fdl.season_id IS NULL;
