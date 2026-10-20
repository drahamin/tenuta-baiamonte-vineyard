<?php
declare(strict_types=1);

final class ReleaseVerifier
{
    public static function envelope(string $json,string $publicKeyBase64):array
    {
        if(!extension_loaded('sodium'))throw new RuntimeException('sodium extension required');
        $envelope=json_decode($json,true,16,JSON_THROW_ON_ERROR);
        if(!is_array($envelope)||($envelope['schema']??null)!==1)throw new RuntimeException('unsupported envelope schema');
        $signature=$envelope['signature']??null;
        if(!is_array($signature)||($signature['algorithm']??null)!=='Ed25519')throw new RuntimeException('unsupported signature algorithm');
        if(!preg_match('/^[A-Za-z0-9._-]{1,64}$/',(string)($signature['key_id']??'')))throw new RuntimeException('invalid signing key id');
        $payload=base64_decode((string)($envelope['payload_base64']??''),true);
        $signed=base64_decode((string)($signature['value_base64']??''),true);
        $public=base64_decode($publicKeyBase64,true);
        if($payload===false||$signed===false||$public===false||strlen($signed)!==SODIUM_CRYPTO_SIGN_BYTES||strlen($public)!==SODIUM_CRYPTO_SIGN_PUBLICKEYBYTES)throw new RuntimeException('invalid release signature encoding');
        if(!sodium_crypto_sign_verify_detached($signed,$payload,$public))throw new RuntimeException('release signature verification failed');
        $result=json_decode($payload,true,16,JSON_THROW_ON_ERROR);
        if(!is_array($result)||($result['schema']??null)!==1||($result['product']??null)!=='baiamonte-secondary')throw new RuntimeException('invalid release payload');
        if(!preg_match('/^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$/',(string)($result['version']??'')))throw new RuntimeException('invalid release version');
        if(!preg_match('/^[0-9]+(?:\.[0-9]+){2}(?:[0-9A-Za-z._-]*)$/',(string)($result['source_app_version']??'')))throw new RuntimeException('invalid source application version');
        if(!preg_match('/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/',(string)($result['source_commit']??'')))throw new RuntimeException('invalid source commit');
        if(!is_bool($result['schema_changes_required']??null))throw new RuntimeException('missing schema change declaration');
        if(($result['publisher_checks']['javascript_syntax']??null)!=='passed')throw new RuntimeException('publisher JavaScript check missing');
        $artifact=$result['artifact']??null;
        if(!is_array($artifact)||basename((string)($artifact['filename']??''))!==($artifact['filename']??null)||!preg_match('/^[a-f0-9]{64}$/',(string)($artifact['sha256']??''))||(int)($artifact['size']??0)<1)throw new RuntimeException('invalid artifact declaration');
        return $result;
    }

    public static function artifact(array $payload,string $artifactPath):void
    {
        $artifact=$payload['artifact'];
        if(!is_file($artifactPath)||basename($artifactPath)!==$artifact['filename'])throw new RuntimeException('artifact filename mismatch');
        if(filesize($artifactPath)!==(int)$artifact['size'])throw new RuntimeException('artifact size mismatch');
        if(!hash_equals((string)$artifact['sha256'],hash_file('sha256',$artifactPath)))throw new RuntimeException('artifact checksum mismatch');
    }

    public static function status(array $payload,string $currentVersion,int $supportedContract):array
    {
        $minimum=(int)($payload['remote_contract_min']??0);
        $maximum=(int)($payload['remote_contract_max']??0);
        if($minimum<1||$maximum<$minimum||$supportedContract<$minimum||$supportedContract>$maximum)throw new RuntimeException('remote contract incompatible');
        return [
            'ok'=>true,
            'update_available'=>version_compare((string)$payload['version'],$currentVersion,'>'),
            'current_version'=>$currentVersion,
            'release_version'=>$payload['version'],
            'key_id'=>$payload['_key_id']??null,
            'artifact'=>$payload['artifact'],
            'migrations'=>array_values(array_map(static fn(array $item):string=>(string)($item['id']??''),array_filter($payload['migrations']??[],'is_array'))),
        ];
    }
}
