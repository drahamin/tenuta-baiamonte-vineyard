CREATE TABLE sync_state (
    singleton TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    active_snapshot_id CHAR(36) NULL,
    last_success_at DATETIME(6) NULL,
    source_generated_at DATETIME(6) NULL,
    last_error TEXT NULL,
    CONSTRAINT sync_state_singleton CHECK (singleton = 1)
) ENGINE=InnoDB;
INSERT INTO sync_state(singleton) VALUES (1);

CREATE TABLE snapshots (
    snapshot_id CHAR(36) NOT NULL PRIMARY KEY,
    source_generated_at DATETIME(6) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    record_count INT UNSIGNED NOT NULL,
    body_sha256 CHAR(64) NOT NULL UNIQUE,
    status ENUM('loading','active','retired','failed') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE replica_records (
    snapshot_id CHAR(36) NOT NULL,
    object_name VARCHAR(96) NOT NULL,
    record_id VARCHAR(191) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL,
    source_updated_at DATETIME(6) NULL,
    data_json JSON NOT NULL,
    PRIMARY KEY(snapshot_id, object_name, record_id),
    KEY replica_records_object_idx(snapshot_id, object_name),
    CONSTRAINT replica_records_snapshot_fk FOREIGN KEY(snapshot_id)
        REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE commands (
    command_id CHAR(36) NOT NULL PRIMARY KEY,
    command_type VARCHAR(64) NOT NULL,
    object_name VARCHAR(96) NOT NULL,
    record_id VARCHAR(191) NOT NULL,
    expected_revision BIGINT UNSIGNED NULL,
    payload_json JSON NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    client_created_at DATETIME(6) NOT NULL,
    received_at DATETIME(6) NOT NULL,
    status ENUM('pending','leased','applied','conflict','rejected') NOT NULL,
    lease_until DATETIME(6) NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    result_json JSON NULL,
    completed_at DATETIME(6) NULL,
    KEY commands_status_idx(status, received_at)
) ENGINE=InnoDB;

CREATE TABLE audit_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    occurred_at DATETIME(6) NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    action VARCHAR(96) NOT NULL,
    entity_type VARCHAR(96) NOT NULL,
    entity_id VARCHAR(191) NOT NULL,
    details_json JSON NOT NULL,
    KEY audit_entity_idx(entity_type, entity_id, occurred_at)
) ENGINE=InnoDB;

CREATE TABLE app_users (
    user_id CHAR(36) NOT NULL PRIMARY KEY,
    ha_user_id VARCHAR(191) NULL UNIQUE,
    username VARCHAR(191) NOT NULL UNIQUE,
    display_name VARCHAR(191) NOT NULL,
    role ENUM('viewer','operator','admin') NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL,
    last_ha_login_at DATETIME(6) NULL
) ENGINE=InnoDB;

CREATE TABLE web_sessions (
    session_hash CHAR(64) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    csrf_hash CHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    auth_method ENUM('ha','passkey','recovery') NOT NULL,
    revoked_at DATETIME(6) NULL,
    KEY web_sessions_user_idx(user_id, expires_at),
    CONSTRAINT web_sessions_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE recovery_codes (
    code_id CHAR(36) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    code_hash VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    used_at DATETIME(6) NULL,
    CONSTRAINT recovery_codes_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE oauth_states (
    state_hash CHAR(64) NOT NULL PRIMARY KEY,
    verifier_value VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    used_at DATETIME(6) NULL
) ENGINE=InnoDB;

CREATE TABLE passkey_credentials (
    credential_id VARBINARY(1024) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    public_key_pem TEXT NOT NULL,
    sign_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    transports_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    last_used_at DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    KEY passkey_credentials_user_idx(user_id, revoked_at),
    CONSTRAINT passkey_credentials_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE webauthn_challenges (
    challenge_hash CHAR(64) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NULL,
    purpose ENUM('register','authenticate') NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    used_at DATETIME(6) NULL,
    CONSTRAINT webauthn_challenges_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE camera_snapshot_requests (
    request_uuid CHAR(36) NOT NULL PRIMARY KEY,
    camera_id VARCHAR(96) NOT NULL,
    actor_id CHAR(36) NOT NULL,
    status ENUM('pending','leased','ready','consumed','failed','expired') NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    lease_until DATETIME(6) NULL,
    ready_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    failure_code VARCHAR(64) NULL,
    KEY camera_requests_queue_idx(status, expires_at, created_at),
    KEY camera_requests_actor_idx(actor_id, created_at),
    CONSTRAINT camera_requests_actor_fk FOREIGN KEY(actor_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE camera_snapshot_tickets (
    request_uuid CHAR(36) NOT NULL PRIMARY KEY,
    signed_path TEXT NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    KEY camera_tickets_expiry_idx(expires_at)
) ENGINE=MEMORY;
