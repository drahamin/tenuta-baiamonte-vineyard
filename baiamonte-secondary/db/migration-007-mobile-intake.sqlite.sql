CREATE TABLE mobile_session_capabilities (
    token_hash TEXT NOT NULL,
    capability TEXT NOT NULL CHECK (capability IN ('intake.submit')),
    granted_at TEXT NOT NULL,
    PRIMARY KEY(token_hash,capability),
    FOREIGN KEY(token_hash) REFERENCES mobile_sessions(token_hash) ON DELETE CASCADE
);

CREATE TABLE mobile_intake_reports (
    report_uuid TEXT PRIMARY KEY,
    estate_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    origin_token_hash TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    client_created_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    source_timezone TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    correction_of_report_uuid TEXT NULL,
    attachment_count INTEGER NOT NULL DEFAULT 0,
    reserved_attachment_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review','leased','accepted','rejected','conflict')),
    revision INTEGER NOT NULL DEFAULT 1,
    lease_token_hash TEXT NULL,
    lease_until TEXT NULL,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    result_json TEXT NULL,
    resolved_at TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(actor_id,report_uuid),
    FOREIGN KEY(actor_id) REFERENCES app_users(user_id),
    FOREIGN KEY(origin_token_hash) REFERENCES mobile_sessions(token_hash),
    FOREIGN KEY(correction_of_report_uuid) REFERENCES mobile_intake_reports(report_uuid)
);
CREATE INDEX mobile_intake_queue ON mobile_intake_reports(estate_id,status,received_at);
CREATE INDEX mobile_intake_actor_status ON mobile_intake_reports(actor_id,status,updated_at);

CREATE TABLE mobile_intake_attachments (
    attachment_uuid TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    report_uuid TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image/jpeg','image/png','application/pdf')),
    byte_count INTEGER NOT NULL,
    original_filename TEXT NULL,
    stored_path TEXT NOT NULL,
    upload_state TEXT NOT NULL DEFAULT 'reserved' CHECK (upload_state IN ('reserved','complete')),
    uploaded_at TEXT NOT NULL,
    forwarded_at TEXT NULL,
    delete_requested_at TEXT NULL,
    cleanup_attempts INTEGER NOT NULL DEFAULT 0,
    cleanup_next_at TEXT NULL,
    cleanup_last_error TEXT NULL,
    deleted_at TEXT NULL,
    UNIQUE(report_uuid,file_sha256),
    UNIQUE(report_uuid,upload_id),
    FOREIGN KEY(report_uuid) REFERENCES mobile_intake_reports(report_uuid)
);

CREATE TABLE mobile_intake_request_nonces (
    nonce_hash TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    request_method TEXT NOT NULL,
    request_path TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    claimed_at TEXT NOT NULL
);
CREATE INDEX mobile_intake_nonce_expiry ON mobile_intake_request_nonces(expires_at);
