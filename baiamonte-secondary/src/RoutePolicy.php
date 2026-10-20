<?php
declare(strict_types=1);

final class RoutePolicy
{
    /** @return 'public-auth'|'sync-hmac'|'session' */
    public static function protection(string $path): string
    {
        if(in_array($path,['/erp','/erp/','/erp/assets/app.js','/erp/assets/app.css','/erp/assets/ha-shell.css','/erp/assets/harvest.css','/erp/assets/harvest.js','/erp/assets/icon-192.png','/erp/assets/icon-512.png','/erp/assets/apple-touch-icon.png','/erp/assets/baiamonte-logo-transparent.png','/erp/site.webmanifest','/erp/auth/start','/erp/auth/callback','/erp/auth/recovery','/erp/auth/passkey/options','/erp/auth/passkey/verify'],true))return 'public-auth';
        if(str_starts_with($path,'/erp/sync/'))return 'sync-hmac';
        return 'session';
    }
}
