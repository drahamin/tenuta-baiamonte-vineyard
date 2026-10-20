ALTER TABLE web_sessions MODIFY auth_method ENUM('ha','passkey','recovery') NOT NULL;
ALTER TABLE oauth_states CHANGE verifier_hash verifier_value VARCHAR(128) NOT NULL;
