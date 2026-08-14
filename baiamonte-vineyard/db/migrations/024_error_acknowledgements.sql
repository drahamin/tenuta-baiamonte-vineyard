CREATE TABLE IF NOT EXISTS error_acknowledgements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    estate_id CHAR(36) NOT NULL,
    error_kind VARCHAR(20) NOT NULL,
    record_id VARCHAR(64) NOT NULL,
    acknowledged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    acknowledged_by VARCHAR(190) NOT NULL,
    note VARCHAR(500) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_error_acknowledgement (estate_id, error_kind, record_id),
    KEY ix_error_acknowledgement_time (estate_id, acknowledged_at),
    CONSTRAINT fk_error_acknowledgement_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
