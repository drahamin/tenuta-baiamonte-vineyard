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

-- This table contains only a one-time 30-second Home Assistant signed path.
-- It never stores image bytes and is intentionally lost on database restart.
CREATE TABLE camera_snapshot_tickets (
    request_uuid CHAR(36) NOT NULL PRIMARY KEY,
    signed_path TEXT NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    KEY camera_tickets_expiry_idx(expires_at)
) ENGINE=MEMORY;
