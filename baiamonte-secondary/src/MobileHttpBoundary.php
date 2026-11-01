<?php
declare(strict_types=1);

final class MobileHttpBoundary
{
    public static function stateCookieName(string $prefix,string $oauthState):string
    {
        if(!preg_match('/^[A-Za-z0-9_-]{43,128}$/D',$oauthState))throw new AuthenticationRequired('authentication required');
        return $prefix.'_'.substr(hash('sha256',$oauthState),0,16);
    }

    public static function callbackLocation(string $redirectUri,string $code,string $state):string
    {
        if(!hash_equals(MobileAuthContract::REDIRECT_URI,$redirectUri)||!preg_match('/^[A-Za-z0-9_-]{43}$/D',$code)||!preg_match('/^[A-Za-z0-9_-]{43}$/D',$state))throw new AuthenticationRequired('authentication required');
        return $redirectUri.'#'.http_build_query(['code'=>$code,'state'=>$state],'','&',PHP_QUERY_RFC3986);
    }

    /** @param array<string,mixed> $server */
    public static function bearer(array $server):string
    {
        $header=trim((string)($server['HTTP_AUTHORIZATION']??''));
        if(!preg_match('/^Bearer ([A-Za-z0-9_-]{43})$/D',$header,$match))throw new AuthenticationRequired('authentication required');
        return $match[1];
    }

    /** @param array<string,mixed> $server */
    public static function rejectBearerOutsideMobile(array $server,string $protection):void
    {
        if(trim((string)($server['HTTP_AUTHORIZATION']??''))!==''&&$protection!=='mobile-bearer')throw new AuthenticationRequired('authentication required');
    }
}
