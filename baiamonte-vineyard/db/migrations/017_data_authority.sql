CREATE TABLE IF NOT EXISTS data_authority_domains (
  estate_id CHAR(36) NOT NULL,
  domain_code VARCHAR(80) NOT NULL,
  authoritative_system VARCHAR(80) NOT NULL,
  migration_source VARCHAR(255) NULL,
  write_policy VARCHAR(255) NOT NULL,
  effective_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  notes TEXT NULL,
  PRIMARY KEY (estate_id,domain_code),
  CONSTRAINT fk_data_authority_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO data_authority_domains (estate_id,domain_code,authoritative_system,migration_source,write_policy,notes) VALUES
('00000000-0000-4000-8000-000000000001','vineyard','MariaDB','Tenuta Baiamonte workbook','Write through Vineyard Operations, approved AI review, or authenticated API','Workbook rows remain available as migration evidence.'),
('00000000-0000-4000-8000-000000000001','harvest','MariaDB','Tenuta Baiamonte workbook','Write through the quick harvest flow or authenticated API','Weights and crate counts are operational records.'),
('00000000-0000-4000-8000-000000000001','cellar','MariaDB','Tenuta Baiamonte workbook','Write through the cellar flow, sensors, approved AI review, or authenticated API','Enologist approval remains required for cellar decisions.'),
('00000000-0000-4000-8000-000000000001','labor','MariaDB','Tenuta Baiamonte workbook','Write through the contractor-hours quick form or authenticated API','Designed for short field entry.'),
('00000000-0000-4000-8000-000000000001','laboratory','MariaDB','Tenuta Baiamonte workbook and source reports','Write through document intake, review, manual correction, or authenticated API','Original reports remain evidence, and reviewed database values drive trends.'),
('00000000-0000-4000-8000-000000000001','planning','MariaDB','Tenuta Baiamonte workbook','Write through tasks, issues, decisions, projections, or approved AI review','Google Calendar and Tasks are supporting views, not the authority.'),
('00000000-0000-4000-8000-000000000001','finance','Fatture in Cloud',NULL,'Read-only synchronization into MariaDB','Fatture in Cloud remains authoritative for accounting.')
ON DUPLICATE KEY UPDATE authoritative_system=VALUES(authoritative_system),migration_source=VALUES(migration_source),write_policy=VALUES(write_policy),notes=VALUES(notes);
