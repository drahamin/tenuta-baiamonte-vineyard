-- PROPOSAL ONLY. Not loaded by production bootstrap or migration tooling.
CREATE TABLE mobile_domain_session_capabilities (
    token_hash CHAR(64) NOT NULL,
    capability VARCHAR(64) NOT NULL,
    granted_at DATETIME(6) NOT NULL,
    PRIMARY KEY(token_hash,capability),
    CONSTRAINT mobile_domain_cap_session_fk FOREIGN KEY(token_hash) REFERENCES mobile_sessions(token_hash) ON DELETE CASCADE,
    CONSTRAINT mobile_domain_cap_name_ck CHECK (capability IN ('timeclock.submit','cellar.operations.submit'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

CREATE TABLE mobile_pending_domain_actions (
    action_uuid CHAR(36) NOT NULL PRIMARY KEY,
    workflow VARCHAR(16) NOT NULL,
    estate_id CHAR(36) NOT NULL,
    actor_id CHAR(36) NOT NULL,
    actor_username VARCHAR(80) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    origin_token_hash CHAR(64) NOT NULL,
    required_capability VARCHAR(64) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    payload_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending_validation',
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    lease_token_hash CHAR(64) NULL,
    lease_until DATETIME(6) NULL,
    delivery_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    result_json JSON NULL,
    resolved_at DATETIME(6) NULL,
    received_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    KEY mobile_pending_domain_queue(estate_id,status,received_at),
    KEY mobile_pending_domain_actor(actor_id,status,updated_at),
    CONSTRAINT mobile_pending_domain_actor_fk FOREIGN KEY(actor_id) REFERENCES app_users(user_id),
    CONSTRAINT mobile_pending_domain_session_fk FOREIGN KEY(origin_token_hash) REFERENCES mobile_sessions(token_hash),
    CONSTRAINT mobile_pending_domain_workflow_ck CHECK (workflow IN ('timeclock','cellar')),
    CONSTRAINT mobile_pending_domain_cap_ck CHECK (required_capability IN ('timeclock.submit','cellar.operations.submit')),
    CONSTRAINT mobile_pending_domain_status_ck CHECK (status IN ('pending_validation','leased','accepted','rejected','conflict'))
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
