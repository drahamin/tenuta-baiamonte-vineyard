<?php
declare(strict_types=1);

final class MobileReadPolicy
{
    private const READ_PATHS=[
        '/erp/mobile/v1/me',
        '/erp/mobile/v1/status',
        '/erp/mobile/v1/catalog',
        '/erp/mobile/v1/records',
        '/erp/mobile/v1/weather',
        '/erp/mobile/v1/calendar',
        '/erp/mobile/v1/directory',
        '/erp/mobile/v1/enology/readings',
    ];

    public static function allows(string $method,string $path):bool
    {
        if(strtoupper($method)==='GET'&&in_array($path,self::READ_PATHS,true))return true;
        return strtoupper($method)==='POST'&&$path==='/erp/mobile/v1/session/revoke';
    }
}
