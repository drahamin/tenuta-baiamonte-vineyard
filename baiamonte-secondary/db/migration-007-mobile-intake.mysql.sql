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
    origin_token_hash CHAR(64) NOT NULL,
    entry_kind VARCHAR(40) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    client_created_at DATETIME(6) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    source_timezone VARCHAR(64) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    payload_json JSON NOT NULL,
    correction_of_report_uuid CHAR(36) NULL,
    attachment_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
    reserved_attachment_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
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
    CONSTRAINT mobile_intake_origin_session_fk FOREIGN KEY(origin_token_hash) REFERENCES mobile_sessions(token_hash),
    CONSTRAINT mobile_intake_correction_fk FOREIGN KEY(correction_of_report_uuid) REFERENCES mobile_intake_reports(report_uuid) ON DELETE RESTRICT,
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
    delete_requested_at DATETIME(6) NULL,
    cleanup_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    cleanup_next_at DATETIME(6) NULL,
    cleanup_last_error VARCHAR(160) NULL,
    deleted_at DATETIME(6) NULL,
    UNIQUE KEY mobile_intake_attachment_digest(report_uuid,file_sha256),
    CONSTRAINT mobile_intake_attachment_report_fk FOREIGN KEY(report_uuid) REFERENCES mobile_intake_reports(report_uuid) ON DELETE RESTRICT,
    CONSTRAINT mobile_intake_attachment_type_ck CHECK (media_type IN ('image/jpeg','image/png','application/pdf'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

CREATE TABLE mobile_intake_request_nonces (
    nonce_hash CHAR(64) NOT NULL PRIMARY KEY,
    key_id VARCHAR(64) NOT NULL,
    request_method VARCHAR(12) NOT NULL,
    request_path VARCHAR(255) NOT NULL,
    issued_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    claimed_at DATETIME(6) NOT NULL,
    KEY mobile_intake_nonce_expiry(expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
