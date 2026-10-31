<?php
declare(strict_types=1);

final class MobileAuthContract
{
    public const CLIENT_ID='com.cantinabaiamonte.vineyard';
    public const REDIRECT_URI='baiamonte-vineyard://auth/callback';
    public const SCOPE='replica.read';
    public const HANDOFF_TTL_SECONDS=300;
    public const SESSION_TTL_SECONDS=3600;

    /** @return array<string,mixed> */
    public static function payload():array
    {
        return [
            'version'=>1,
            'enabled'=>false,
            'routes_registered'=>true,
            'controller_implemented'=>true,
            'identity_provider'=>'home_assistant',
            'client_id'=>self::CLIENT_ID,
            'redirect_uri'=>self::REDIRECT_URI,
            'handoff'=>[
                'authorization_code_ttl_seconds'=>self::HANDOFF_TTL_SECONDS,
                'pkce_method'=>'S256',
                'one_time'=>true,
                'ha_oauth_state_bound'=>true,
                'browser_cookie_bound'=>true,
            ],
            'session'=>[
                'token_type'=>'Bearer',
                'scope'=>self::SCOPE,
                'ttl_seconds'=>self::SESSION_TTL_SECONDS,
                'server_stores'=>'sha256_hash_only',
            ],
            'read_routes'=>[
                'GET /erp/mobile/v1/me',
                'GET /erp/mobile/v1/status',
                'GET /erp/mobile/v1/catalog',
                'GET /erp/mobile/v1/records',
                'GET /erp/mobile/v1/weather',
                'GET /erp/mobile/v1/calendar (separately gated)',
                'GET /erp/mobile/v1/directory (separately gated)',
                'GET /erp/mobile/v1/enology/readings (separately gated)',
            ],
            'auth_routes'=>[
                'GET /erp/auth/mobile/start',
                'POST /erp/auth/mobile/exchange',
                'GET /erp/auth/callback (existing HA callback)',
            ],
            'revoke_route'=>'POST /erp/mobile/v1/session/revoke',
            'write_routes'=>[
                'POST /erp/mobile/v1/intake/reports (feature and capability gated)',
                'POST /erp/mobile/v1/intake/reports/{uuid}/attachments (feature and capability gated)',
            ],
            'role_source'=>'app_users',
            'capability_evaluation'=>'server_role_intersect_token_capabilities',
            'initial_capabilities'=>[self::SCOPE],
            'optional_capabilities'=>['intake.submit'],
            'wildcard_capabilities'=>false,
            'email_matching'=>false,
        ];
    }
}
