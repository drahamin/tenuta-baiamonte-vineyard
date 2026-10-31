<?php
declare(strict_types=1);

final class MobileIntakeSyncAuth
{
    public static function verifyAndClaim(PDO $db,string $method,string $path,string $rawBody,string $keyId,string $timestamp,string $nonce,string $signature,string $secret,int $now,int $window=120):void
    {
        $method=strtoupper($method);
        $validPath=$path==='/erp/sync/mobile-intake/requests'||preg_match('#^/erp/sync/mobile-intake/(?:results|attachments)/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$#iD',$path)===1;
        if($method!=='POST'||!$validPath)throw new RuntimeException('invalid intake sync target');
        if(!preg_match('/^[A-Za-z0-9._-]{1,64}$/D',$keyId)||!ctype_digit($timestamp)||abs($now-(int)$timestamp)>$window)throw new RuntimeException('stale intake sync request');
        if(!preg_match('/^[A-Za-z0-9_-]{43}$/D',$nonce)||!str_starts_with($signature,'sha256='))throw new RuntimeException('invalid intake sync authentication');
        $bodyHash=hash('sha256',$rawBody);$canonical=$method."\n".$path."\n".$keyId."\n".$timestamp."\n".$nonce."\n".$bodyHash;
        $expected=hash_hmac('sha256',$canonical,$secret);if(!hash_equals($expected,substr($signature,7)))throw new RuntimeException('invalid intake sync signature');
        $claimed=DatabaseTime::from(gmdate('Y-m-d\TH:i:s\Z',$now));$issued=DatabaseTime::from(gmdate('Y-m-d\TH:i:s\Z',(int)$timestamp));$expires=DatabaseTime::from(gmdate('Y-m-d\TH:i:s\Z',$now+$window));
        $db->beginTransaction();
        try{
            $db->prepare('DELETE FROM mobile_intake_request_nonces WHERE expires_at<?')->execute([$claimed]);
            $insert=$db->prepare('INSERT INTO mobile_intake_request_nonces(nonce_hash,key_id,request_method,request_path,issued_at,expires_at,claimed_at) VALUES(?,?,?,?,?,?,?)');
            try{$insert->execute([hash('sha256',$nonce),$keyId,$method,$path,$issued,$expires,$claimed]);}catch(PDOException $error){throw new RuntimeException('intake sync replay rejected',0,$error);}
            $db->commit();
        }catch(Throwable $error){if($db->inTransaction())$db->rollBack();throw $error;}
    }
}
