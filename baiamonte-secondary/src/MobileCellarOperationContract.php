<?php
declare(strict_types=1);

/** Validation-only cellar command contract. It never performs dosing, transfer, filtration, inventory, or device control. */
final class MobileCellarOperationContract
{
    public const VERSION='baiamonte.mobile-cellar-operation.v1';
    private const KINDS=['racking.v1','product_addition.v1','filtration.v1','tank_work.v1'];
    private const FILTER_METHODS=['plate','crossflow','cartridge','pad','earth'];
    private const TANK_WORK=['sampling','mixing','lees_stirring','cap_management','cleaning'];
    private string $estateId;

    public function __construct(string $estateId)
    {
        if(!$this->uuid($estateId,false))throw new InvalidArgumentException('valid mobile estate boundary is required');$this->estateId=strtolower($estateId);
    }

    /** @param array<string,mixed> $request @param array<string,mixed> $actor @return array<string,mixed> */
    public function validate(array $request,array $actor):array
    {
        foreach(array_keys($request) as $key)if(!in_array((string)$key,['operation_uuid','kind','estate_id','occurred_at','client_created_at','source_timezone','expected_revisions','payload','correction_of_operation_uuid'],true))throw new InvalidArgumentException('unsupported cellar operation field: '.$key);
        if(($actor['role']??null)!=='admin'||!$this->identifier((string)($actor['user_id']??''))||trim((string)($actor['username']??''))==='')throw new DomainException('administrator cellar authority is required');
        if(!hash_equals($this->estateId,strtolower((string)($request['estate_id']??''))))throw new DomainException('cellar estate boundary does not match');
        $uuid=$this->requiredUuid((string)($request['operation_uuid']??''),'operation_uuid');$kind=(string)($request['kind']??'');if(!in_array($kind,self::KINDS,true))throw new InvalidArgumentException('unsupported cellar operation kind');
        $timezone=(string)($request['source_timezone']??'');if(!in_array($timezone,DateTimeZone::listIdentifiers(DateTimeZone::ALL_WITH_BC),true))throw new InvalidArgumentException('source_timezone must be an existing IANA timezone');
        if(!is_array($request['payload']??null)||$this->isList($request['payload']))throw new InvalidArgumentException('cellar payload must be an object');$payload=$this->payload($kind,$request['payload']);$revisions=$this->revisions($payload['revision_entities'],$request['expected_revisions']??null);unset($payload['revision_entities']);
        $correction=null;if(isset($request['correction_of_operation_uuid'])&&$request['correction_of_operation_uuid']!==null)$correction=$this->requiredUuid((string)$request['correction_of_operation_uuid'],'correction_of_operation_uuid');
        return ['contract'=>self::VERSION,'operation_uuid'=>$uuid,'idempotency_key'=>$uuid,'kind'=>$kind,'estate_id'=>$this->estateId,'occurred_at'=>$this->time((string)($request['occurred_at']??''),'occurred_at'),'client_created_at'=>$this->time((string)($request['client_created_at']??''),'client_created_at'),'source_timezone'=>$timezone,'expected_revisions'=>$revisions,'payload'=>$payload,'correction_of_operation_uuid'=>$correction,'actor'=>['user_id'=>(string)$actor['user_id'],'username'=>trim((string)$actor['username']),'server_role'=>'admin'],'status'=>'pending_validation','applied'=>false,'inventory_committed'=>false,'device_control'=>false,'side_effects'=>[]];
    }

    /** @param array<string,mixed> $value @return array<string,mixed> */
    private function payload(string $kind,array $value):array
    {
        if($kind==='racking.v1'){
            $this->exact($value,['source_container_id','target_container_id','wine_lot_id','transfer_volume_l','expected_loss_l','note'],['source_container_id','target_container_id','wine_lot_id','transfer_volume_l','expected_loss_l']);$source=$this->id($value['source_container_id']);$target=$this->id($value['target_container_id']);if(hash_equals($source,$target))throw new InvalidArgumentException('racking source and target must differ');$volume=$this->positive($value['transfer_volume_l'],'transfer_volume_l');$loss=$this->nonnegative($value['expected_loss_l'],'expected_loss_l');if($loss>$volume)throw new InvalidArgumentException('expected racking loss cannot exceed transfer volume');return ['source_container_id'=>$source,'target_container_id'=>$target,'wine_lot_id'=>$this->id($value['wine_lot_id']),'transfer_volume_l'=>$volume,'expected_loss_l'=>$loss,'note'=>$this->note($value['note']??null),'revision_entities'=>['source_container_id','target_container_id','wine_lot_id']];
        }
        if($kind==='product_addition.v1'){
            $this->exact($value,['container_id','wine_lot_id','product_id','quantity','unit','reason','note'],['container_id','wine_lot_id','product_id','quantity','unit','reason']);$unit=(string)$value['unit'];if(!in_array($unit,['gram','kilogram','millilitre','litre'],true))throw new InvalidArgumentException('unsupported product quantity unit');return ['container_id'=>$this->id($value['container_id']),'wine_lot_id'=>$this->id($value['wine_lot_id']),'product_id'=>$this->id($value['product_id']),'quantity'=>$this->positive($value['quantity'],'quantity'),'unit'=>$unit,'reason'=>$this->text($value['reason'],500),'note'=>$this->note($value['note']??null),'revision_entities'=>['container_id','wine_lot_id','product_id']];
        }
        if($kind==='filtration.v1'){
            $this->exact($value,['container_id','wine_lot_id','method','processed_volume_l','expected_loss_l','note'],['container_id','wine_lot_id','method','processed_volume_l','expected_loss_l']);$method=(string)$value['method'];if(!in_array($method,self::FILTER_METHODS,true))throw new InvalidArgumentException('unsupported filtration method');$volume=$this->positive($value['processed_volume_l'],'processed_volume_l');$loss=$this->nonnegative($value['expected_loss_l'],'expected_loss_l');if($loss>$volume)throw new InvalidArgumentException('expected filtration loss cannot exceed processed volume');return ['container_id'=>$this->id($value['container_id']),'wine_lot_id'=>$this->id($value['wine_lot_id']),'method'=>$method,'processed_volume_l'=>$volume,'expected_loss_l'=>$loss,'note'=>$this->note($value['note']??null),'revision_entities'=>['container_id','wine_lot_id']];
        }
        $this->exact($value,['container_id','wine_lot_id','operation','duration_minutes','note'],['container_id','wine_lot_id','operation']);$operation=(string)$value['operation'];if(!in_array($operation,self::TANK_WORK,true))throw new InvalidArgumentException('unsupported tank work operation');$duration=$value['duration_minutes']??null;if($duration!==null&&(!is_int($duration)||$duration<1||$duration>1440))throw new InvalidArgumentException('duration_minutes must be 1 through 1440');return ['container_id'=>$this->id($value['container_id']),'wine_lot_id'=>$this->id($value['wine_lot_id']),'operation'=>$operation,'duration_minutes'=>$duration,'note'=>$this->note($value['note']??null),'revision_entities'=>['container_id','wine_lot_id']];
    }

    /** @param list<string> $entities @return array<string,string> */
    private function revisions(array $entities,mixed $value):array{if(!is_array($value)||$this->isList($value)||count($value)!==count($entities))throw new InvalidArgumentException('expected_revisions must exactly match operation entities');$out=[];foreach($entities as $entity){$revision=$value[$entity]??null;if(!is_string($revision)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new InvalidArgumentException('expected revision is required for '.$entity);$out[$entity]=$revision;}if(array_diff_key($value,$out)||array_diff_key($out,$value))throw new InvalidArgumentException('expected_revisions must exactly match operation entities');return $out;}
    /** @param list<string> $allowed @param list<string> $required */
    private function exact(array $value,array $allowed,array $required):void{foreach(array_keys($value) as $key)if(!in_array((string)$key,$allowed,true))throw new InvalidArgumentException('unsupported cellar payload field: '.$key);foreach($required as $key)if(!array_key_exists($key,$value))throw new InvalidArgumentException($key.' is required');}
    private function requiredUuid(string $value,string $field):string{if(!$this->uuid($value,true))throw new InvalidArgumentException($field.' must be a UUIDv4');return strtolower($value);}
    private function uuid(string $value,bool $v4):bool{return preg_match($v4?'/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD':'/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value)===1;}
    private function identifier(string $value):bool{return preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$value)===1;}
    private function id(mixed $value):string{if(!is_string($value)||!$this->identifier($value))throw new InvalidArgumentException('invalid cellar entity reference');return $value;}
    private function positive(mixed $value,string $field):float{if((!is_int($value)&&!is_float($value))||!is_finite((float)$value)||(float)$value<=0||(float)$value>10000000)throw new InvalidArgumentException($field.' must be a positive bounded number');return (float)$value;}
    private function nonnegative(mixed $value,string $field):float{if((!is_int($value)&&!is_float($value))||!is_finite((float)$value)||(float)$value<0||(float)$value>10000000)throw new InvalidArgumentException($field.' must be a bounded nonnegative number');return (float)$value;}
    private function text(mixed $value,int $limit):string{if(!is_string($value)||trim($value)==='')throw new InvalidArgumentException('required cellar text is missing');return mb_substr(trim($value),0,$limit);}
    private function note(mixed $value):?string{if($value===null)return null;if(!is_string($value))throw new InvalidArgumentException('note must be a string');$value=trim($value);return $value===''?null:mb_substr($value,0,2000);}
    private function time(string $value,string $field):string{if(!preg_match('/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/D',$value,$parts)||!checkdate((int)$parts[2],(int)$parts[3],(int)$parts[1])||(int)$parts[4]>23||(int)$parts[5]>59||(int)$parts[6]>59)throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset');try{$parsed=new DateTimeImmutable($value);}catch(Throwable $error){throw new InvalidArgumentException($field.' must be a real RFC3339 timestamp with offset',0,$error);}return $parsed->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s.u\Z');}
    /** @param array<mixed> $value */
    private function isList(array $value):bool{$expected=0;foreach($value as $key=>$unused){if($key!==$expected++)return false;}return true;}
}
