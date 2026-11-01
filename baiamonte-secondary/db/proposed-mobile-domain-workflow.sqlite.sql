-- PROPOSAL ONLY. Not loaded by production bootstrap or migration tooling.
CREATE TABLE mobile_domain_session_capabilities (
    token_hash TEXT NOT NULL,
    capability TEXT NOT NULL CHECK (capability IN ('timeclock.submit','cellar.operations.submit')),
    granted_at TEXT NOT NULL,
    PRIMARY KEY(token_hash,capability),
    FOREIGN KEY(token_hash) REFERENCES mobile_sessions(token_hash) ON DELETE CASCADE
);

CREATE TABLE mobile_pending_domain_actions (
    action_uuid TEXT PRIMARY KEY,
    workflow TEXT NOT NULL CHECK (workflow IN ('timeclock','cellar')),
    estate_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    origin_token_hash TEXT NOT NULL,
    required_capability TEXT NOT NULL CHECK (required_capability IN ('timeclock.submit','cellar.operations.submit')),
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_validation' CHECK (status IN ('pending_validation','leased','accepted','rejected','conflict')),
    revision INTEGER NOT NULL DEFAULT 1,
    lease_token_hash TEXT NULL,
    lease_until TEXT NULL,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    result_json TEXT NULL,
    resolved_at TEXT NULL,
    received_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(actor_id) REFERENCES app_users(user_id),
    FOREIGN KEY(origin_token_hash) REFERENCES mobile_sessions(token_hash)
);
CREATE INDEX mobile_pending_domain_queue ON mobile_pending_domain_actions(estate_id,status,received_at);
CREATE INDEX mobile_pending_domain_actor ON mobile_pending_domain_actions(actor_id,status,updated_at);
