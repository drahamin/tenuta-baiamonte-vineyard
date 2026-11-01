PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE mobile_session_capabilities_v2 (
    token_hash TEXT NOT NULL,
    capability TEXT NOT NULL CHECK (capability IN ('intake.submit','light.control')),
    granted_at TEXT NOT NULL,
    PRIMARY KEY(token_hash,capability),
    FOREIGN KEY(token_hash) REFERENCES mobile_sessions(token_hash) ON DELETE CASCADE
);
INSERT INTO mobile_session_capabilities_v2(token_hash,capability,granted_at)
SELECT token_hash,capability,granted_at FROM mobile_session_capabilities;
DROP TABLE mobile_session_capabilities;
ALTER TABLE mobile_session_capabilities_v2 RENAME TO mobile_session_capabilities;
COMMIT;
PRAGMA foreign_keys=ON;
