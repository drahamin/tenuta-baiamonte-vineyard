CREATE TABLE mobile_auth_transactions (
    state_hash TEXT PRIMARY KEY,
    oauth_state_hash TEXT NOT NULL UNIQUE,
    client_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    user_id TEXT NULL,
    authorization_code_hash TEXT NULL,
    authorized_at TEXT NULL,
    consumed_at TEXT NULL,
    exchange_attempts INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);
CREATE INDEX mobile_auth_transactions_expiry_idx ON mobile_auth_transactions(expires_at);

CREATE TABLE mobile_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope = 'replica.read'),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(user_id)
);
CREATE INDEX mobile_sessions_user_idx ON mobile_sessions(user_id,expires_at);
