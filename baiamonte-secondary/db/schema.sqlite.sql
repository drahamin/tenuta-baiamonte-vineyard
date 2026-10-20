PRAGMA foreign_keys = ON;

CREATE TABLE sync_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    active_snapshot_id TEXT NULL,
    last_success_at TEXT NULL,
    source_generated_at TEXT NULL,
    last_error TEXT NULL
);
INSERT INTO sync_state(singleton) VALUES (1);

CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source_generated_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    body_sha256 TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('loading','active','retired','failed'))
);

CREATE TABLE replica_records (
    snapshot_id TEXT NOT NULL,
    object_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 0),
    source_updated_at TEXT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, object_name, record_id),
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);
CREATE INDEX replica_records_object_idx
    ON replica_records(snapshot_id, object_name);

CREATE TABLE commands (
    command_id TEXT PRIMARY KEY,
    command_type TEXT NOT NULL,
    object_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    expected_revision INTEGER NULL,
    payload_json TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    client_created_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','leased','applied','conflict','rejected')),
    lease_until TEXT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_json TEXT NULL,
    completed_at TEXT NULL
);
CREATE INDEX commands_status_idx ON commands(status, received_at);

CREATE TABLE audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE app_users (
    user_id TEXT PRIMARY KEY,
    ha_user_id TEXT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer','operator','admin')),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_ha_login_at TEXT NULL
);

CREATE TABLE web_sessions (
    session_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    auth_method TEXT NOT NULL CHECK (auth_method IN ('ha','passkey','recovery')),
    revoked_at TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);
CREATE INDEX web_sessions_user_idx ON web_sessions(user_id, expires_at);

CREATE TABLE recovery_codes (
    code_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used_at TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);

CREATE TABLE oauth_states (
    state_hash TEXT PRIMARY KEY,
    verifier_value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT NULL
);

CREATE TABLE passkey_credentials (
    credential_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    public_key_pem TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NULL,
    revoked_at TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);
CREATE INDEX passkey_credentials_user_idx ON passkey_credentials(user_id, revoked_at);

CREATE TABLE webauthn_challenges (
    challenge_hash TEXT PRIMARY KEY,
    user_id TEXT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('register','authenticate')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);

CREATE TABLE camera_snapshot_requests (
    request_uuid TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    lease_until TEXT NULL,
    ready_at TEXT NULL,
    completed_at TEXT NULL,
    failure_code TEXT NULL,
    FOREIGN KEY(actor_id) REFERENCES app_users(user_id)
);
CREATE INDEX camera_requests_queue_idx ON camera_snapshot_requests(status,expires_at,created_at);
CREATE INDEX camera_requests_actor_idx ON camera_snapshot_requests(actor_id,created_at);

CREATE TABLE camera_snapshot_tickets (
    request_uuid TEXT PRIMARY KEY,
    signed_path TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX camera_tickets_expiry_idx ON camera_snapshot_tickets(expires_at);
