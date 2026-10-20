<?php
declare(strict_types=1);

final class SyncAuth
{
    public static function verify(string $rawBody, string $timestamp, string $signature, string $secret, int $now, int $window=300): void
    {
        if(!ctype_digit($timestamp) || abs($now-(int)$timestamp)>$window) throw new RuntimeException('stale sync request');
        if(!str_starts_with($signature,'sha256=')) throw new RuntimeException('invalid signature format');
        $expected=hash_hmac('sha256',$timestamp."\n".$rawBody,$secret);
        if(!hash_equals($expected,substr($signature,7))) throw new RuntimeException('invalid signature');
    }

    public static function decodeBody(string $rawBody,string $contentEncoding,int $maxCompressed=67108864,int $maxDecoded=536870912):string
    {
        if(strlen($rawBody)>$maxCompressed)throw new RuntimeException('compressed sync payload exceeds limit');
        $encoding=strtolower(trim($contentEncoding));
        if($encoding==='')$decoded=$rawBody;
        elseif($encoding==='gzip'){
            $decoded=gzdecode($rawBody,$maxDecoded+1);
            if($decoded===false)throw new RuntimeException('invalid gzip sync payload');
        }else throw new RuntimeException('unsupported sync content encoding');
        if(strlen($decoded)>$maxDecoded)throw new RuntimeException('expanded sync payload exceeds limit');
        return $decoded;
    }
}
