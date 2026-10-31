<?php
declare(strict_types=1);

return [
    'db_dsn' => getenv('BAIAMONTE_DB_DSN') ?: '',
    'db_user' => getenv('BAIAMONTE_DB_USER') ?: '',
    'db_password' => getenv('BAIAMONTE_DB_PASSWORD') ?: '',
    'sync_key_id' => getenv('BAIAMONTE_SYNC_KEY_ID') ?: '',
    'sync_hmac_key' => getenv('BAIAMONTE_SYNC_HMAC_KEY') ?: '',
    'sync_enabled' => false,
    'camera_sync_enabled' => false,
    'camera_sync_key_id' => 'baiamonte-camera-1',
    'camera_sync_hmac_key' => getenv('BAIAMONTE_CAMERA_HMAC_KEY') ?: '',
    'release_update_enabled' => false,
    'release_manifest_url' => 'https://cantinabaiamonte.com/private-releases/baiamonte-secondary/latest.envelope.json',
    'release_host' => 'cantinabaiamonte.com',
    'release_public_key_base64' => getenv('BAIAMONTE_RELEASE_PUBLIC_KEY') ?: '',
    'release_key_id' => 'baiamonte-secondary-owner-2026-1',
    'release_supported_contract' => 1,
    'session_cookie' => 'baiamonte_secondary',
    'base_path' => '/erp',
    'public_origin' => 'https://cantinabaiamonte.com',
    'ha_base_url' => 'https://your-home-assistant.example',
    'ha_client_id' => 'https://cantinabaiamonte.com/erp/',
    'ha_redirect_uri' => 'https://cantinabaiamonte.com/erp/auth/callback',
    'ha_local_username' => 'approved-user',
    'ha_initial_display_name' => 'Approved User',
    'webauthn_rp_id' => 'cantinabaiamonte.com',
    'offline_revalidation_seconds' => 604800,
    'csrf_cookie' => 'baiamonte_csrf',
    'oauth_state_cookie' => 'baiamonte_oauth_state',
    // Staged only: routes remain unregistered until owner-approved activation.
    'mobile_auth_enabled' => false,
    'mobile_client_id' => 'com.cantinabaiamonte.vineyard',
    'mobile_redirect_uri' => 'baiamonte-vineyard://auth/callback',
    'mobile_state_cookie' => 'baiamonte_mobile_state',
    'mobile_handoff_ttl_seconds' => 300,
    'mobile_session_ttl_seconds' => 3600,
    // Exact estate boundary for deny-by-default mobile row filtering.
    'mobile_estate_id' => getenv('BAIAMONTE_MOBILE_ESTATE_ID') ?: '',
    'session_ttl_seconds' => 43200,
    'max_snapshot_age_seconds' => 7200,
    // Replace only from the verified, permitted reporting manifest.
    'allowed_objects' => [],
    'excluded_fields' => [
        'cellar_operations' => ['amount'],
        'work_activities' => ['cost_eur'],
    ],
    'allowed_command_types' => [
        'record.create',
        'record.update',
        'inventory.transfer',
    ],
    // Populate only in the private production config after privacy approval.
    'camera_allowlist' => [],
];
