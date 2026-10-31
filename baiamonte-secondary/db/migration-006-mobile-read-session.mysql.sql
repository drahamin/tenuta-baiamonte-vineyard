CREATE TABLE mobile_auth_transactions (
    state_hash CHAR(64) NOT NULL PRIMARY KEY,
    oauth_state_hash CHAR(64) NOT NULL UNIQUE,
    client_id VARCHAR(191) NOT NULL,
    redirect_uri VARCHAR(255) NOT NULL,
    code_challenge CHAR(43) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    user_id CHAR(36) NULL,
    authorization_code_hash CHAR(64) NULL,
    authorized_at DATETIME(6) NULL,
    consumed_at DATETIME(6) NULL,
    exchange_attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    KEY mobile_auth_transactions_expiry_idx(expires_at),
    CONSTRAINT mobile_auth_transactions_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id)
) ENGINE=InnoDB;

CREATE TABLE mobile_sessions (
    token_hash CHAR(64) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    client_id VARCHAR(191) NOT NULL,
    scope VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    KEY mobile_sessions_user_idx(user_id,expires_at),
    CONSTRAINT mobile_sessions_user_fk FOREIGN KEY(user_id) REFERENCES app_users(user_id),
    CONSTRAINT mobile_sessions_scope_ck CHECK (scope = 'replica.read')
) ENGINE=InnoDB;
