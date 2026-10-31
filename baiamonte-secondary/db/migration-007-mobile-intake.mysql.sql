CREATE TABLE mobile_session_capabilities (
    token_hash CHAR(64) NOT NULL,
    capability VARCHAR(64) NOT NULL,
    granted_at DATETIME(6) NOT NULL,
    PRIMARY KEY(token_hash,capability),
    CONSTRAINT mobile_session_capability_session_fk FOREIGN KEY(token_hash) REFERENCES mobile_sessions(token_hash) ON DELETE CASCADE,
    CONSTRAINT mobile_session_capability_name_ck CHECK (capability IN ('intake.submit'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

CREATE TABLE mobile_intake_reports (
    report_uuid CHAR(36) NOT NULL PRIMARY KEY,
    estate_id CHAR(36) NOT NULL,
    actor_id CHAR(36) NOT NULL,
    actor_username VARCHAR(80) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    entry_kind VARCHAR(40) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    client_created_at DATETIME(6) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    source_timezone VARCHAR(64) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    payload_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    lease_token_hash CHAR(64) NULL,
    lease_until DATETIME(6) NULL,
    delivery_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    result_json JSON NULL,
    resolved_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    UNIQUE KEY mobile_intake_actor_uuid(actor_id,report_uuid),
    KEY mobile_intake_queue(estate_id,status,received_at),
    KEY mobile_intake_actor_status(actor_id,status,updated_at),
    CONSTRAINT mobile_intake_actor_fk FOREIGN KEY(actor_id) REFERENCES app_users(user_id),
    CONSTRAINT mobile_intake_status_ck CHECK (status IN ('pending_review','leased','accepted','rejected','conflict'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

CREATE TABLE mobile_intake_attachments (
    attachment_uuid CHAR(36) NOT NULL PRIMARY KEY,
    report_uuid CHAR(36) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    media_type VARCHAR(64) NOT NULL,
    byte_count INT UNSIGNED NOT NULL,
    original_filename VARCHAR(180) NULL,
    stored_path VARCHAR(512) NOT NULL,
    uploaded_at DATETIME(6) NOT NULL,
    forwarded_at DATETIME(6) NULL,
    deleted_at DATETIME(6) NULL,
    UNIQUE KEY mobile_intake_attachment_digest(report_uuid,file_sha256),
    CONSTRAINT mobile_intake_attachment_report_fk FOREIGN KEY(report_uuid) REFERENCES mobile_intake_reports(report_uuid) ON DELETE RESTRICT,
    CONSTRAINT mobile_intake_attachment_type_ck CHECK (media_type IN ('image/jpeg','image/png','application/pdf'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
