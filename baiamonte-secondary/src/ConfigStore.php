<?php
declare(strict_types=1);

final class ConfigStore
{
    /** @param array<string,mixed> $current @return array<string,mixed> */
    public static function updateSync(string $path,array $current,array $input):array
    {
        if(($current['sync_enabled']??false)!==true && !array_key_exists('enabled',$input))$input['enabled']=false;
        $enabled=(bool)($input['enabled']??false);
        $keyId=trim((string)($input['key_id']??($current['sync_key_id']??'')));
        $secret=trim((string)($input['secret']??''));
        if($secret==='')$secret=(string)($current['sync_hmac_key']??'');
        if(!preg_match('/^[A-Za-z0-9._-]{1,64}$/D',$keyId))throw new InvalidArgumentException('invalid sync key id');
        if($secret!==''&&!self::validSecret($secret))throw new InvalidArgumentException('sync key must be a 256-bit base64url value');
        if($enabled&&$secret==='')throw new InvalidArgumentException('sync key is required before enabling');
        if(!is_file($path)||!is_writable($path))throw new RuntimeException('private configuration is not writable');
        $updated=array_replace($current,['sync_enabled'=>$enabled,'sync_key_id'=>$keyId,'sync_hmac_key'=>$secret]);
        $backup=$path.'.pre-sync-'.gmdate('Ymd\THis\Z');
        if(!copy($path,$backup))throw new RuntimeException('configuration backup failed');
        chmod($backup,0600);
        $temporary=$path.'.new';
        $source="<?php\ndeclare(strict_types=1);\nreturn ".var_export($updated,true).";\n";
        if(file_put_contents($temporary,$source,LOCK_EX)===false)throw new RuntimeException('configuration write failed');
        chmod($temporary,0600);
        if(!rename($temporary,$path))throw new RuntimeException('configuration activation failed');
        return ['enabled'=>$enabled,'key_id'=>$keyId,'secret_configured'=>$secret!==''];
    }

    private static function validSecret(string $value):bool
    {
        if(!preg_match('/^[A-Za-z0-9_-]{43}$/D',$value))return false;
        $decoded=base64_decode(strtr($value,'-_','+/').'=',true);
        return $decoded!==false&&strlen($decoded)===32;
    }
}
