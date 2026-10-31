<?php
declare(strict_types=1);

final class HttpSecurity
{
    public static function headers(?string $haBaseUrl=null):void
    {
        header('Cache-Control: no-store');
        header('Pragma: no-cache');
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: DENY');
        header('Referrer-Policy: no-referrer');
        $img="img-src 'self' data:";
        if($haBaseUrl!==null){$parts=parse_url($haBaseUrl);if(is_array($parts)&&($parts['scheme']??'')==='https'&&isset($parts['host']))$img.=' https://'.$parts['host'];}
        header("Content-Security-Policy: default-src 'self'; ".$img."; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
        header('Permissions-Policy: camera=(), microphone=(), geolocation=()');
        header('Strict-Transport-Security: max-age=31536000; includeSubDomains');
    }

    public static function setSessionCookie(string $name,string $value,int $expires):void
    {
        // OAuth returns from another site. Lax permits the new session on the
        // immediate top-level redirect to /erp/app; write routes still require
        // the independent CSRF header/cookie pair.
        setcookie($name,$value,['expires'=>$expires,'path'=>'/erp','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);
    }

    public static function setCsrfCookie(string $name,string $value,int $expires):void
    {
        setcookie($name,$value,['expires'=>$expires,'path'=>'/erp','secure'=>true,'httponly'=>false,'samesite'=>'Strict']);
    }

    /** OAuth is a top-level cross-site return, so this one short-lived cookie is Lax. */
    public static function setOAuthStateCookie(string $name,string $value,int $expires):void
    {
        setcookie($name,$value,['expires'=>$expires,'path'=>'/erp/auth/callback','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);
    }

    public static function setMobileStateCookie(string $name,string $value,int $expires):void
    {
        setcookie($name,$value,['expires'=>$expires,'path'=>'/erp/auth/callback','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);
    }
}
