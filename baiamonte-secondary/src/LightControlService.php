<?php
declare(strict_types=1);

final class LightControlService
{
    public const ALLOWLIST=[
        'light.switch_1_lightbulb'=>'Kitchen overhead',
        'light.switch_2_lightbulb'=>'Warehouse',
        'light.switch_3_lightbulb'=>'Toilette',
        'light.switch_4_lightbulb'=>'Palmento',
        'light.switch_5_lightbulb'=>'Patio',
        'light.switch_6_lightbulb'=>'Patio strip',
        'light.switch_7_lightbulb'=>'Kitchen sink',
        'light.switch_8_lightbulb'=>'Fox Den overhead',
    ];

    public function __construct(private PDO $db,private bool $enabled,private string $approvedUsername='approved-owner',private int $maxSnapshotAgeSeconds=7200){}

    /** @return array{enabled:bool,lights:array<string,string>,observations:list<array<string,mixed>>,freshness:array<string,mixed>} */
    public function catalog(array $actor,string $now):array
    {
        $permitted=$this->enabled&&$this->authorized($actor);
        if(!$permitted)return ['enabled'=>false,'lights'=>[],'observations'=>[],'freshness'=>['source_generated_at'=>null,'data_age_seconds'=>null,'stale'=>true]];
        [$observations,$freshness]=$this->observations($now);
        return ['enabled'=>true,'lights'=>self::ALLOWLIST,'observations'=>$observations,'freshness'=>$freshness];
    }

    /** @return array{command_id:string,status:string,deduplicated:bool,expires_at:string} */
    public function create(array $actor,array $request,string $now,string $originKind,string $originHash):array
    {
        if(!$this->enabled)throw new DomainException('light control is disabled');
        if(!$this->authorized($actor))throw new DomainException('administrator_required');
        if(!in_array($originKind,['web','mobile'],true)||!preg_match('/^[0-9a-f]{64}$/D',$originHash))throw new DomainException('authenticated origin is required');
        if(array_diff_key($request,array_flip(['request_uuid','entity_id','desired_state','expected_state','expected_observed_at'])))throw new InvalidArgumentException('unsupported light control field');
        $id=$this->uuid((string)($request['request_uuid']??''));$entity=(string)($request['entity_id']??'');
        $desired=(string)($request['desired_state']??'');$expected=(string)($request['expected_state']??'');$observed=(string)($request['expected_observed_at']??'');
        if(!isset(self::ALLOWLIST[$entity]))throw new InvalidArgumentException('light is not permitted');
        if(!in_array($desired,['on','off'],true)||!in_array($expected,['on','off'],true)||$desired===$expected)throw new InvalidArgumentException('light state transition is invalid');
        if($observed===''||strtotime($observed)===false)throw new InvalidArgumentException('expected observation timestamp is invalid');
        $now=DatabaseTime::from($now);$expires=DatabaseTime::from($now,30);
        $payload=['desired_state'=>$desired,'expected_state'=>$expected,'expected_observed_at'=>$observed,'expires_at'=>$expires,'_origin_kind'=>$originKind,'_origin_hash'=>$originHash];$json=$this->json($payload);
        $existing=$this->db->prepare('SELECT command_type,object_name,record_id,payload_json,status FROM commands WHERE command_id=?');$existing->execute([$id]);$row=$existing->fetch(PDO::FETCH_ASSOC);
        if($row){$stored=json_decode((string)$row['payload_json'],true,16,JSON_THROW_ON_ERROR);$storedRequest=$stored;unset($storedRequest['expires_at']);$same=$row['command_type']==='light.control'&&$row['object_name']==='ha_light'&&$row['record_id']===$entity&&hash_equals($this->json(['desired_state'=>$desired,'expected_state'=>$expected,'expected_observed_at'=>$observed,'_origin_kind'=>$originKind,'_origin_hash'=>$originHash]),$this->json($storedRequest));if(!$same)throw new DomainException('command UUID reused with different content');return ['command_id'=>$id,'status'=>(string)$row['status'],'deduplicated'=>true,'expires_at'=>(string)$stored['expires_at']];}
        [$observations,$freshness]=$this->observations($now);$current=null;foreach($observations as $candidate)if(hash_equals($entity,(string)$candidate['entity_id'])){$current=$candidate;break;}
        if(($freshness['stale']??true)===true||!is_array($current)||!in_array($current['state']??null,['on','off'],true)||!is_string($current['observed_at']??null))throw new DomainException('verified light observation is unavailable');
        if(!hash_equals($expected,(string)$current['state'])||!hash_equals($observed,(string)$current['observed_at']))throw new DomainException('light observation changed; refresh required');
        $this->db->beginTransaction();
        try{
            if($this->db->getAttribute(PDO::ATTR_DRIVER_NAME)==='mysql'){$lock=$this->db->prepare('SELECT user_id FROM app_users WHERE user_id=? FOR UPDATE');$lock->execute([(string)$actor['user_id']]);}
            $pending=$this->db->prepare("SELECT COUNT(*) FROM commands WHERE actor_id=? AND command_type='light.control' AND status IN ('pending','leased')");$pending->execute([(string)$actor['user_id']]);if((int)$pending->fetchColumn()>0)throw new DomainException('a light control request is already pending');
            $q=$this->db->prepare("INSERT INTO commands(command_id,command_type,object_name,record_id,expected_revision,payload_json,actor_id,client_created_at,received_at,status) VALUES(?,'light.control','ha_light',?,NULL,?,?,?,?, 'pending')");
            $q->execute([$id,$entity,$json,(string)$actor['user_id'],$now,$now]);
            $this->audit($now,(string)$actor['user_id'],'light.control.queued',$id,['entity_id'=>$entity,'light_name'=>self::ALLOWLIST[$entity],'expected_state'=>$expected,'desired_state'=>$desired,'expires_at'=>$expires]);$this->db->commit();
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
        return ['command_id'=>$id,'status'=>'pending','deduplicated'=>false,'expires_at'=>$expires];
    }

    private function authorized(array $actor):bool{return ($actor['enabled']??true)&&($actor['role']??'')==='admin'&&is_string($actor['username']??null)&&hash_equals($this->approvedUsername,(string)$actor['username']);}
    /** @return array{0:list<array<string,mixed>>,1:array<string,mixed>} */
    private function observations(string $now):array
    {
        $state=$this->db->query('SELECT active_snapshot_id,source_generated_at FROM sync_state WHERE singleton=1')->fetch(PDO::FETCH_ASSOC);$generated=is_array($state)&&is_string($state['source_generated_at']??null)?(string)$state['source_generated_at']:null;
        $age=$generated!==null&&strtotime($generated)!==false&&strtotime($now)!==false?max(0,strtotime($now)-strtotime($generated)):null;$stale=$age===null||$age>$this->maxSnapshotAgeSeconds;$byId=[];
        if(is_array($state)&&is_string($state['active_snapshot_id']??null)&&$state['active_snapshot_id']!==''){$q=$this->db->prepare("SELECT record_id,source_updated_at,data_json FROM replica_records WHERE snapshot_id=? AND object_name='ro_light_status'");$q->execute([(string)$state['active_snapshot_id']]);foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){$entity=(string)$row['record_id'];if(!isset(self::ALLOWLIST[$entity]))continue;try{$data=json_decode((string)$row['data_json'],true,16,JSON_THROW_ON_ERROR);}catch(JsonException){continue;}$value=is_array($data)?(string)($data['state']??''):'';$observed=is_array($data)&&is_string($data['observed_at']??null)?(string)$data['observed_at']:(is_string($row['source_updated_at']??null)?(string)$row['source_updated_at']:null);if(!in_array($value,['on','off'],true)){$value='unavailable';$observed=null;}if($observed!==null&&strtotime($observed)===false)$observed=null;$byId[$entity]=['entity_id'=>$entity,'name'=>self::ALLOWLIST[$entity],'state'=>$value,'observed_at'=>$observed,'controllable'=>!$stale&&$value!=='unavailable'&&$observed!==null];}}
        $out=[];foreach(self::ALLOWLIST as $entity=>$name)$out[]=$byId[$entity]??['entity_id'=>$entity,'name'=>$name,'state'=>'unavailable','observed_at'=>null,'controllable'=>false];
        return [$out,['source_generated_at'=>$generated,'data_age_seconds'=>$age,'stale'=>$stale]];
    }
    private function audit(string $now,string $actor,string $action,string $id,array $details):void{$q=$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)');$q->execute([$now,$actor,$action,'light_control',$id,$this->json($details)]);}
    private function uuid(string $value):string{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$value))throw new InvalidArgumentException('invalid UUID');return strtolower($value);}
    private function json(mixed $value):string{return json_encode($value,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);}
}
