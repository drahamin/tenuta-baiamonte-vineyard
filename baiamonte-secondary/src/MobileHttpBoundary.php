<?php
declare(strict_types=1);

final class MobileHttpBoundary
{
    public static function stateCookieName(string $prefix,string $oauthState):string
    {
        if(!preg_match('/^[A-Za-z0-9_-]{43,128}$/D',$oauthState))throw new RuntimeException('authentication required');
        return $prefix.'_'.substr(hash('sha256',$oauthState),0,16);
    }

    /** @param array<string,mixed> $server */
    public static function bearer(array $server):string
    {
        $header=trim((string)($server['HTTP_AUTHORIZATION']??''));
        if(!preg_match('/^Bearer ([A-Za-z0-9_-]{43})$/D',$header,$match))throw new RuntimeException('authentication required');
        return $match[1];
    }

    /** @param array<string,mixed> $server */
    public static function rejectBearerOutsideMobile(array $server,string $protection):void
    {
        if(trim((string)($server['HTTP_AUTHORIZATION']??''))!==''&&$protection!=='mobile-bearer')throw new RuntimeException('authentication required');
    }
}
