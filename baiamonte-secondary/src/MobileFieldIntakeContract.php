<?php
declare(strict_types=1);

final class MobileFieldIntakeContract
{
    public const VERSION='baiamonte.mobile-intake.v1';
    private const KINDS=['field_observation','damage_report','work_report','cellar_note','agronomy_note','enology_reading'];
    private const MEASUREMENTS=[
        'babo'=>'degree_babo','temperature_c'=>'celsius','density_sg'=>'specific_gravity','brix'=>'degree_brix','ph'=>'pH',
        'affected_area_pct'=>'percent','estimated_yield_loss_pct'=>'percent','rainfall_mm'=>'millimetres','wind_kph'=>'kilometres_per_hour',
    ];
    private string $estateId;

    public function __construct(string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');$this->estateId=$estateId;
    }

    /** Validation only. This class never persists, approves or applies a domain record. @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function validate(array $payload,array $actor):array
    {
        $role=(string)($actor['role']??'');$username=trim((string)($actor['username']??''));
        if(!in_array($role,['operator','admin'],true)||$username==='')throw new DomainException('mobile intake role is not permitted');
        $allowed=['report_uuid','kind','estate_id','occurred_at','client_created_at','source_timezone','entities','expected_revisions','measurements','note','instrument','attachments','correction_of_report_uuid'];
        foreach(array_keys($payload) as $key)if(!in_array((string)$key,$allowed,true))throw new InvalidArgumentException('unsupported intake field: '.$key);
        $uuid=$this->uuid((string)($payload['report_uuid']??''),'report_uuid');$kind=(string)($payload['kind']??'');
        if(!in_array($kind,self::KINDS,true))throw new InvalidArgumentException('unsupported intake kind');
        if(!hash_equals($this->estateId,(string)($payload['estate_id']??'')))throw new DomainException('intake estate boundary does not match');
        $occurred=$this->time((string)($payload['occurred_at']??''),'occurred_at');$created=$this->time((string)($payload['client_created_at']??''),'client_created_at');
        $timezone=trim((string)($payload['source_timezone']??''));if(!in_array($timezone,DateTimeZone::listIdentifiers(DateTimeZone::ALL_WITH_BC),true))throw new InvalidArgumentException('source_timezone must be an existing IANA timezone');
        $entities=$this->entities($kind,$payload['entities']??null);$revisions=$this->revisions($entities,$payload['expected_revisions']??null);
        $measurements=$this->measurements($kind,$payload['measurements']??[]);
        $attachments=$this->attachments($payload['attachments']??[]);
        $correction=null;if(isset($payload['correction_of_report_uuid'])&&$payload['correction_of_report_uuid']!==null)$correction=$this->uuid((string)$payload['correction_of_report_uuid'],'correction_of_report_uuid');
        $instrument=$payload['instrument']??null;if($instrument!==null&&!is_array($instrument))throw new InvalidArgumentException('instrument must be an object');
        if(is_array($instrument)){
            foreach(array_keys($instrument) as $key)if(!in_array((string)$key,['name','identifier','calibrated_at'],true))throw new InvalidArgumentException('unsupported instrument field');
            $instrument=['name'=>$this->shortText($instrument['name']??null,120),'identifier'=>$this->shortText($instrument['identifier']??null,120),'calibrated_at'=>isset($instrument['calibrated_at'])?$this->time((string)$instrument['calibrated_at'],'instrument.calibrated_at'):null];
        }
        return ['contract'=>self::VERSION,'report_uuid'=>$uuid,'idempotency_key'=>$uuid,'kind'=>$kind,'estate_id'=>$this->estateId,'occurred_at'=>$occurred,'client_created_at'=>$created,'source_timezone'=>$timezone,'entities'=>$entities,'expected_revisions'=>$revisions,'measurements'=>$measurements,'note'=>$this->shortText($payload['note']??null,4000),'instrument'=>$instrument,'attachments'=>$attachments,'correction_of_report_uuid'=>$correction,'author'=>['username'=>$username,'server_role'=>$role],'status'=>'pending_review','applied'=>false,'side_effects'=>[],'immutable_raw_submission'=>true];
    }

    /** @return array<string,string> */
    private function entities(string $kind,mixed $value):array
    {
        if(!is_array($value))throw new InvalidArgumentException('entities must be an object');$allowed=['block_id','task_id','work_activity_id','container_id','wine_lot_id'];$out=[];
        foreach($value as $key=>$id){if(!in_array((string)$key,$allowed,true)||!is_string($id)||!preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$id))throw new InvalidArgumentException('invalid entity reference');$out[(string)$key]=$id;}
        $required=match($kind){'field_observation','damage_report','agronomy_note'=>['block_id'],'enology_reading'=>['container_id','wine_lot_id'],default=>[]};foreach($required as $key)if(!isset($out[$key]))throw new InvalidArgumentException($key.' is required');
        if($kind==='work_report'&&!isset($out['task_id'])&&!isset($out['work_activity_id']))throw new InvalidArgumentException('task_id or work_activity_id is required');
        if($kind==='cellar_note'&&!isset($out['container_id'])&&!isset($out['wine_lot_id']))throw new InvalidArgumentException('container_id or wine_lot_id is required');return $out;
    }
    /** @param array<string,string> $entities @return array<string,string> */
    private function revisions(array $entities,mixed $value):array
    {
        if(!is_array($value)||$this->isList($value)||count($value)!==count($entities)||array_diff_key($value,$entities)||array_diff_key($entities,$value))throw new InvalidArgumentException('expected_revisions must exactly match entities');$out=[];
        foreach($entities as $key=>$unused){$revision=$value[$key]??null;if(!is_string($revision)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new InvalidArgumentException('expected revision is required for '.$key);$out[$key]=$revision;}return $out;
    }
    /** @return list<array{code:string,value:float,unit:string}> */
    private function measurements(string $kind,mixed $value):array
    {
        if(!is_array($value)||!$this->isList($value)||count($value)>24)throw new InvalidArgumentException('measurements must be a bounded list');$out=[];
        foreach($value as $row){if(!is_array($row)||$this->isList($row))throw new InvalidArgumentException('measurement must be an object');foreach(array_keys($row) as $key)if(!in_array((string)$key,['code','value','unit'],true))throw new InvalidArgumentException('unsupported measurement field');$code=(string)($row['code']??'');$unit=(string)($row['unit']??'');$number=$row['value']??null;if(!isset(self::MEASUREMENTS[$code])||!hash_equals(self::MEASUREMENTS[$code],$unit)||(!is_int($number)&&!is_float($number))||!is_finite((float)$number))throw new InvalidArgumentException('invalid typed measurement');$out[]=['code'=>$code,'value'=>(float)$number,'unit'=>$unit];}
        if($kind==='enology_reading'){
            $enology=['babo','temperature_c','density_sg','brix','ph'];
            if(!$out)throw new InvalidArgumentException('enology reading requires a supported measurement');
            foreach($out as $row)if(!in_array($row['code'],$enology,true))throw new InvalidArgumentException('measurement is not permitted for enology reading');
        }
        return $out;
    }
    /** @return list<array<string,mixed>> */
    private function attachments(mixed $value):array
    {
        if(!is_array($value)||!$this->isList($value)||count($value)>5)throw new InvalidArgumentException('attachments must be a bounded list');$out=[];$seen=[];
        foreach($value as $row){
            if(!is_array($row))throw new InvalidArgumentException('attachment descriptor must be an object');
            foreach(array_keys($row) as $key)if(!in_array((string)$key,['sha256','media_type','byte_count','filename'],true))throw new InvalidArgumentException('unsupported attachment descriptor field');
            $sha=strtolower((string)($row['sha256']??''));$mime=(string)($row['media_type']??'');$bytes=filter_var($row['byte_count']??null,FILTER_VALIDATE_INT);if(!preg_match('/^[0-9a-f]{64}$/D',$sha)||!in_array($mime,['image/jpeg','image/png','application/pdf'],true)||$bytes===false||$bytes<1||$bytes>15728640||isset($seen[$sha]))throw new InvalidArgumentException('invalid attachment descriptor');$seen[$sha]=true;$out[]=['sha256'=>$sha,'media_type'=>$mime,'byte_count'=>$bytes,'filename'=>$this->shortText($row['filename']??null,180)];
        }
        return $out;
    }
    private function uuid(string $value,string $field):string{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value))throw new InvalidArgumentException($field.' must be a UUIDv4');return strtolower($value);}
    private function time(string $value,string $field):string{
        if(!preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/D',$value,$parts))throw new InvalidArgumentException($field.' must be strict RFC3339 with offset');
        if(!checkdate((int)$parts[2],(int)$parts[3],(int)$parts[1])||(int)$parts[4]>23||(int)$parts[5]>59||(int)$parts[6]>59)throw new InvalidArgumentException($field.' is not a real timestamp');
        try{$parsed=new DateTimeImmutable($value);}catch(Throwable $error){throw new InvalidArgumentException($field.' is not a real timestamp',0,$error);}
        return $parsed->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s.u\Z');
    }
    private function shortText(mixed $value,int $limit):?string{if($value===null)return null;if(!is_string($value))throw new InvalidArgumentException('text field must be a string');$value=trim($value);return $value===''?null:mb_substr($value,0,$limit);}
    /** PHP 8.0-compatible equivalent of array_is_list(). @param array<mixed> $value */
    private function isList(array $value):bool{$expected=0;foreach($value as $key=>$unused){if($key!==$expected++)return false;}return true;}
}
