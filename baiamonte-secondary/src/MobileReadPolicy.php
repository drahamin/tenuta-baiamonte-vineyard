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
        '/erp/mobile/v1/work',
        '/erp/mobile/v1/review',
        '/erp/mobile/v1/intake/context',
    ];

    public static function allows(string $method,string $path):bool
    {
        if(strtoupper($method)==='GET'){
            if(in_array($path,self::READ_PATHS,true))return true;
            return (bool)preg_match('#^/erp/mobile/v1/intake/reports/[0-9a-f-]{36}$#iD',$path);
        }
        if(strtoupper($method)!=='POST')return false;
        if(in_array($path,['/erp/mobile/v1/session/revoke','/erp/mobile/v1/intake/reports'],true))return true;
        return (bool)preg_match('#^/erp/mobile/v1/intake/reports/[0-9a-f-]{36}/attachments$#iD',$path);
    }
}
