<?php
declare(strict_types=1);

/** Validation-only enrollment/rotation DTO contract. It stores nothing and verifies no signature. */
final class MobileDeviceRenewalContract
{
    public const VERSION='baiamonte.mobile-device-renewal.v1';
    public const ACCESS_SECONDS=3600;
    public const IDLE_SECONDS=86400;
    public const ABSOLUTE_SECONDS=604800;
    public const CHALLENGE_SECONDS=90;
    private string $clientId;

    public function __construct(string $clientId)
    {
        if($clientId==='')throw new InvalidArgumentException('mobile client id is required');$this->clientId=$clientId;
    }

    /** @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function enrollment(array $payload,array $actor):array
    {
        $this->exact($payload,['device_uuid','client_id','algorithm','public_key_spki','renewal_secret_sha256'],['device_uuid','client_id','algorithm','public_key_spki','renewal_secret_sha256'],'enrollment');
        $this->actor($actor);if(!hash_equals($this->clientId,(string)$payload['client_id']))throw new DomainException('device enrollment client does not match');if($payload['algorithm']!=='ES256')throw new InvalidArgumentException('device signing algorithm must be ES256');
        $public=(string)$payload['public_key_spki'];if(!preg_match('/^[A-Za-z0-9_-]{80,256}$/D',$public))throw new InvalidArgumentException('public_key_spki must be bounded base64url');
        return ['contract'=>self::VERSION,'device_uuid'=>$this->uuid((string)$payload['device_uuid'],'device_uuid'),'client_id'=>$this->clientId,'algorithm'=>'ES256','public_key_spki'=>$public,'renewal_secret_sha256'=>$this->digest((string)$payload['renewal_secret_sha256'],'renewal_secret_sha256'),'generation'=>'1','access_lifetime_seconds'=>self::ACCESS_SECONDS,'idle_lifetime_seconds'=>self::IDLE_SECONDS,'absolute_lifetime_seconds'=>self::ABSOLUTE_SECONDS,'challenge_lifetime_seconds'=>self::CHALLENGE_SECONDS,'capability_ceiling'=>['replica.read','commands.read','commands.enqueue'],'private_key_received'=>false,'renewal_secret_received'=>false];
    }

    /** @param array<string,mixed> $payload @return array<string,mixed> */
    public function rotation(array $payload):array
    {
        $this->exact($payload,['device_uuid','generation','challenge','request_uuid','timestamp','current_secret_sha256','next_secret_sha256','signature'],['device_uuid','generation','challenge','request_uuid','timestamp','current_secret_sha256','next_secret_sha256','signature'],'rotation');
        $generation=$payload['generation']??null;if(!is_string($generation)||!preg_match('/^[1-9][0-9]{0,19}$/D',$generation))throw new InvalidArgumentException('generation must be a lossless positive decimal string');
        $challenge=(string)$payload['challenge'];if(!preg_match('/^[A-Za-z0-9_-]{43}$/D',$challenge))throw new InvalidArgumentException('challenge must be a 256-bit base64url value');$signature=(string)$payload['signature'];if(!preg_match('/^[A-Za-z0-9_-]{64,192}$/D',$signature))throw new InvalidArgumentException('signature must be bounded base64url');
        $current=$this->digest((string)$payload['current_secret_sha256'],'current_secret_sha256');$next=$this->digest((string)$payload['next_secret_sha256'],'next_secret_sha256');if(hash_equals($current,$next))throw new InvalidArgumentException('renewal secret must rotate');
        $device=$this->uuid((string)$payload['device_uuid'],'device_uuid');$request=$this->uuid((string)$payload['request_uuid'],'request_uuid');$timestamp=$this->time((string)$payload['timestamp'],'timestamp');$canonical="POST\n/erp/auth/mobile/renew\n".$device."\n".$generation."\n".$challenge."\n".$request."\n".$timestamp."\n".$current."\n".$next;
        return ['contract'=>self::VERSION,'device_uuid'=>$device,'generation'=>$generation,'challenge'=>$challenge,'request_uuid'=>$request,'timestamp'=>$timestamp,'current_secret_sha256'=>$current,'next_secret_sha256'=>$next,'signature'=>$signature,'canonical_message'=>$canonical,'exact_retry_window_seconds'=>120,'atomic_rotation_required'=>true,'capability_ceiling'=>['replica.read','commands.read','commands.enqueue']];
    }

    /** @param array<string,mixed> $actor */
    private function actor(array $actor):void{if(!preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',(string)($actor['user_id']??''))||!in_array((string)($actor['role']??''),['viewer','operator','admin'],true))throw new DomainException('bound enabled mobile actor is required');}
    /** @param list<string> $allowed @param list<string> $required */
    private function exact(array $payload,array $allowed,array $required,string $label):void{foreach(array_keys($payload) as $key)if(!in_array((string)$key,$allowed,true))throw new InvalidArgumentException('unsupported '.$label.' field: '.$key);foreach($required as $key)if(!array_key_exists($key,$payload))throw new InvalidArgumentException($key.' is required');}
    private function uuid(string $value,string $field):string{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value))throw new InvalidArgumentException($field.' must be a UUIDv4');return strtolower($value);}
    private function digest(string $value,string $field):string{$value=strtolower($value);if(!preg_match('/^[0-9a-f]{64}$/D',$value))throw new InvalidArgumentException($field.' must be SHA-256 hex');return $value;}
    private function time(string $value,string $field):string{if(!preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/D',$value,$parts)||!checkdate((int)$parts[2],(int)$parts[3],(int)$parts[1])||(int)$parts[4]>23||(int)$parts[5]>59||(int)$parts[6]>59)throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset');try{$parsed=new DateTimeImmutable($value);}catch(Throwable $error){throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset',0,$error);}return $parsed->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s.u\Z');}
}
