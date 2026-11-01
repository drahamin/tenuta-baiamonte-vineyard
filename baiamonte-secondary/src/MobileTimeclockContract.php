<?php
declare(strict_types=1);

/** Validation-only DTO contract. It does not persist, approve, calculate payroll, or apply a shift. */
final class MobileTimeclockContract
{
    public const VERSION='baiamonte.mobile-timeclock.v1';
    private const EVENTS=['clock_in','break_start','break_end','clock_out'];
    private string $estateId;

    public function __construct(string $estateId)
    {
        if(!$this->uuid($estateId,false))throw new InvalidArgumentException('valid mobile estate boundary is required');$this->estateId=strtolower($estateId);
    }

    /** @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function validate(array $payload,array $actor):array
    {
        $allowed=['event_uuid','estate_id','event_type','shift_uuid','occurred_at','client_created_at','source_timezone','expected_shift_revision','note','correction_of_event_uuid'];
        foreach(array_keys($payload) as $key)if(!in_array((string)$key,$allowed,true))throw new InvalidArgumentException('unsupported timeclock field: '.$key);
        $role=(string)($actor['role']??'');$userId=(string)($actor['user_id']??'');$username=trim((string)($actor['username']??''));$personId=(string)($actor['person_id']??'');
        if(!in_array($role,['operator','admin'],true)||$username===''||!$this->identifier($userId)||!$this->identifier($personId))throw new DomainException('server-bound timeclock identity is required');
        if(!hash_equals($this->estateId,strtolower((string)($payload['estate_id']??''))))throw new DomainException('timeclock estate boundary does not match');
        $eventUuid=$this->requiredUuid((string)($payload['event_uuid']??''),'event_uuid');$shiftUuid=$this->requiredUuid((string)($payload['shift_uuid']??''),'shift_uuid');$event=(string)($payload['event_type']??'');
        if(!in_array($event,self::EVENTS,true))throw new InvalidArgumentException('unsupported timeclock event type');
        $revision=$payload['expected_shift_revision']??null;
        if($event==='clock_in'){
            if($revision!==null)throw new InvalidArgumentException('clock_in cannot claim an existing shift revision');
        }elseif(!is_string($revision)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new InvalidArgumentException('expected_shift_revision is required after clock_in');
        $timezone=(string)($payload['source_timezone']??'');if(!in_array($timezone,DateTimeZone::listIdentifiers(DateTimeZone::ALL_WITH_BC),true))throw new InvalidArgumentException('source_timezone must be an existing IANA timezone');
        $correction=null;if(isset($payload['correction_of_event_uuid'])&&$payload['correction_of_event_uuid']!==null)$correction=$this->requiredUuid((string)$payload['correction_of_event_uuid'],'correction_of_event_uuid');
        return ['contract'=>self::VERSION,'event_uuid'=>$eventUuid,'idempotency_key'=>$eventUuid,'estate_id'=>$this->estateId,'event_type'=>$event,'shift_uuid'=>$shiftUuid,'occurred_at'=>$this->time((string)($payload['occurred_at']??''),'occurred_at'),'client_created_at'=>$this->time((string)($payload['client_created_at']??''),'client_created_at'),'source_timezone'=>$timezone,'expected_shift_revision'=>$revision,'note'=>$this->shortText($payload['note']??null,1000),'correction_of_event_uuid'=>$correction,'actor'=>['user_id'=>$userId,'username'=>$username,'person_id'=>$personId,'server_role'=>$role],'status'=>'pending_validation','applied'=>false,'payroll_approved'=>false,'location_collected'=>false,'side_effects'=>[]];
    }

    private function requiredUuid(string $value,string $field):string{if(!$this->uuid($value,true))throw new InvalidArgumentException($field.' must be a UUIDv4');return strtolower($value);}
    private function uuid(string $value,bool $v4):bool{return preg_match($v4?'/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD':'/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value)===1;}
    private function identifier(string $value):bool{return preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$value)===1;}
    private function time(string $value,string $field):string{if(!preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/D',$value,$parts)||!checkdate((int)$parts[2],(int)$parts[3],(int)$parts[1])||(int)$parts[4]>23||(int)$parts[5]>59||(int)$parts[6]>59)throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset');try{$parsed=new DateTimeImmutable($value);}catch(Throwable $error){throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset',0,$error);}return $parsed->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s.u\Z');}
    private function shortText(mixed $value,int $limit):?string{if($value===null)return null;if(!is_string($value))throw new InvalidArgumentException('note must be a string');$value=trim($value);return $value===''?null:mb_substr($value,0,$limit);}
}
