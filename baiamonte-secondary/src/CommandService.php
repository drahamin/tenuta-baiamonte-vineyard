<?php
declare(strict_types=1);

final class CommandService
{
    /** Reporting-only objects must never enter the offline write queue. */
    private const READ_ONLY_OBJECTS=['olive_harvests'=>true];
    private PDO $db;
    /** @var array<string,true> */
    private array $allowedObjects;
    /** @var array<string,true> */
    private array $allowedTypes;
    private string $approvedUsername;
    private bool $lightControlEnabled;

    /** @param list<string> $allowedObjects @param list<string> $allowedTypes */
    public function __construct(PDO $db, array $allowedObjects, array $allowedTypes, string $approvedUsername, bool $lightControlEnabled=false)
    {
        $this->db = $db;
        $this->allowedObjects = array_fill_keys($allowedObjects, true);
        $this->allowedTypes = array_fill_keys($allowedTypes, true);
        $this->approvedUsername = $approvedUsername;
        $this->lightControlEnabled = $lightControlEnabled;
    }

    /** @param array<string,mixed> $command @return array{command_id:string,status:string,deduplicated:bool} */
    public function enqueue(array $command, string $actorId, string $now): array
    {
        $this->assertAuthorizedActor($actorId);
        $id = $this->uuid((string)($command['command_id'] ?? ''));
        $type = (string)($command['command_type'] ?? '');
        $object = (string)($command['object'] ?? '');
        $recordId = trim((string)($command['record_id'] ?? ''));
        $expected = $command['expected_revision'] ?? null;
        $payload = $command['payload'] ?? null;
        $clientTime = (string)($command['client_created_at'] ?? '');
        if (!isset($this->allowedTypes[$type])) throw new InvalidArgumentException('command type is not permitted');
        if (!isset($this->allowedObjects[$object])) throw new InvalidArgumentException('object is not permitted');
        if (isset(self::READ_ONLY_OBJECTS[$object])) throw new InvalidArgumentException('object is read only');
        if ($recordId === '' || strlen($recordId) > 191) throw new InvalidArgumentException('invalid record id');
        if ($expected !== null && (filter_var($expected, FILTER_VALIDATE_INT) === false || (int)$expected < 0)) throw new InvalidArgumentException('invalid expected revision');
        if ($expected !== null) $expected = (string)(int)$expected;
        if (!is_array($payload)) throw new InvalidArgumentException('payload must be an object');
        if ($clientTime === '' || strtotime($clientTime) === false) throw new InvalidArgumentException('invalid client timestamp');
        if ($type === 'record.update' && $expected === null) throw new InvalidArgumentException('updates require expected revision');
        if ($type === 'inventory.transfer') $this->validateTransfer($payload, $expected);

        $existing = $this->db->prepare('SELECT command_type,object_name,record_id,expected_revision,payload_json,status FROM commands WHERE command_id=?');
        $existing->execute([$id]);
        $row = $existing->fetch(PDO::FETCH_ASSOC);
        $json = $this->json($payload);
        if ($row) {
            $same = $row['command_type'] === $type && $row['object_name'] === $object && $row['record_id'] === $recordId
                && (($row['expected_revision'] === null && $expected === null) || hash_equals((string)$row['expected_revision'], (string)$expected))
                && hash_equals((string)$row['payload_json'], $json);
            if (!$same) throw new DomainException('command UUID reused with different content');
            return ['command_id' => $id, 'status' => (string)$row['status'], 'deduplicated' => true];
        }

        $this->db->beginTransaction();
        try {
            $q = $this->db->prepare('INSERT INTO commands(command_id,command_type,object_name,record_id,expected_revision,payload_json,actor_id,client_created_at,received_at,status) VALUES(?,?,?,?,?,?,?,?,?,?)');
            $q->execute([$id,$type,$object,$recordId,$expected,$json,$actorId,$clientTime,$now,'pending']);
            $this->audit($now,$actorId,'command.queued','command',$id,['type'=>$type,'object'=>$object,'record_id'=>$recordId]);
            $this->db->commit();
        } catch (Throwable $e) {
            if ($this->db->inTransaction()) $this->db->rollBack();
            throw $e;
        }
        return ['command_id'=>$id,'status'=>'pending','deduplicated'=>false];
    }

    /** @return list<array<string,mixed>> */
    public function lease(int $limit, string $leaseUntil, string $now): array
    {
        $limit = max(1, min(100, $limit));$now=DatabaseTime::from($now);$leaseUntil=DatabaseTime::from($leaseUntil);
        $this->db->beginTransaction();
        try {
            $this->db->prepare("UPDATE commands SET status='pending',lease_until=NULL WHERE status='leased' AND lease_until < ?")->execute([$now]);
            $rows = $this->db->query("SELECT c.*,u.username AS actor_username,u.role AS actor_role,u.enabled AS actor_enabled,u.last_ha_login_at AS actor_last_ha_login_at FROM commands c LEFT JOIN app_users u ON u.user_id=c.actor_id WHERE c.status='pending' ORDER BY c.received_at LIMIT ".$limit)->fetchAll(PDO::FETCH_ASSOC);
            $mark = $this->db->prepare("UPDATE commands SET status='leased',lease_until=?,attempt_count=attempt_count+1 WHERE command_id=? AND status='pending'");
            $out=[];
            foreach($rows as $row){
                if($row['command_type']==='light.control'){
                    $payload=json_decode((string)$row['payload_json'],true,16,JSON_THROW_ON_ERROR);$reason=null;
                    if(!$this->lightControlEnabled)$reason='capability_disabled';
                    elseif(!(bool)$row['actor_enabled']||$row['actor_role']!=='admin'||!is_string($row['actor_username'])||!hash_equals($this->approvedUsername,(string)$row['actor_username']))$reason='authority_changed';
                    elseif($row['object_name']!=='ha_light'||!isset(LightControlService::ALLOWLIST[(string)$row['record_id']]))$reason='entity_not_permitted';
                    elseif(!$this->lightOriginAuthorized($row,$payload,$now))$reason='origin_authority_changed';
                    elseif(!is_string($payload['expires_at']??null)||(strtotime((string)$payload['expires_at'])<strtotime($now)&&(int)$row['attempt_count']===0))$reason='expired';
                    if($reason!==null){$reject=$this->db->prepare("UPDATE commands SET status='rejected',result_json=?,completed_at=?,lease_until=NULL WHERE command_id=? AND status='pending'");$reject->execute([$this->json(['reason'=>$reason]),$now,$row['command_id']]);if($reject->rowCount()===1)$this->audit($now,'website-policy','command.rejected','command',(string)$row['command_id'],['reason'=>$reason]);continue;}
                }
                $mark->execute([$leaseUntil,$row['command_id']]);
                if($mark->rowCount()!==1) continue;
                $dispatchPayload=json_decode((string)$row['payload_json'],true,512,JSON_THROW_ON_ERROR);unset($dispatchPayload['_origin_kind'],$dispatchPayload['_origin_hash']);$out[]=[
                    'command_id'=>$row['command_id'],'command_type'=>$row['command_type'],'object'=>$row['object_name'],
                    'record_id'=>$row['record_id'],'expected_revision'=>$row['expected_revision']===null?null:(string)$row['expected_revision'],
                    'payload'=>$dispatchPayload,
                    'actor_id'=>$row['actor_id'],'actor_username'=>$row['actor_username'],'actor_role'=>$row['actor_role'],
                    'actor_enabled'=>(bool)$row['actor_enabled'],'client_created_at'=>$row['client_created_at'],
                ];
            }
            $this->db->commit();
            return $out;
        } catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @param array<string,mixed> $result */
    public function complete(string $commandId, string $status, array $result, string $now): void
    {
        $id=$this->uuid($commandId);
        if(!in_array($status,['applied','conflict','rejected'],true)) throw new InvalidArgumentException('invalid terminal status');
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare("UPDATE commands SET status=?,result_json=?,completed_at=?,lease_until=NULL WHERE command_id=? AND status IN ('pending','leased')");
            $q->execute([$status,$this->json($result),$now,$id]);
            if($q->rowCount()!==1){
                $check=$this->db->prepare('SELECT status,result_json FROM commands WHERE command_id=?');$check->execute([$id]);$old=$check->fetch(PDO::FETCH_ASSOC);
                if(!$old || $old['status']!==$status || !hash_equals((string)$old['result_json'],$this->json($result))) throw new DomainException('invalid or conflicting command completion');
            } else $this->audit($now,'ha-sync','command.'.$status,'command',$id,$result);
            $this->db->commit();
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @return list<array<string,mixed>> */
    public function recentForActor(string $actorId,int $limit=50):array
    {
        $limit=max(1,min(100,$limit));$q=$this->db->prepare('SELECT command_id,command_type,object_name,record_id,expected_revision,client_created_at,received_at,status,attempt_count,result_json,completed_at FROM commands WHERE actor_id=? ORDER BY received_at DESC LIMIT '.$limit);$q->execute([$actorId]);$out=[];
        foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){$row['expected_revision']=$row['expected_revision']===null?null:(string)$row['expected_revision'];$row['attempt_count']=(int)$row['attempt_count'];$row['result']=$row['result_json']===null?null:json_decode((string)$row['result_json'],true,512,JSON_THROW_ON_ERROR);unset($row['result_json']);$out[]=$row;}return $out;
    }

    /** @param array<string,mixed> $payload */
    private function validateTransfer(array $payload, $expected): void
    {
        foreach(['from_record_id','to_record_id','unit'] as $key) if(trim((string)($payload[$key]??''))==='') throw new InvalidArgumentException('transfer missing '.$key);
        if($payload['from_record_id']===$payload['to_record_id']) throw new InvalidArgumentException('transfer endpoints must differ');
        if(!isset($payload['quantity']) || !is_numeric($payload['quantity']) || (float)$payload['quantity']<=0) throw new InvalidArgumentException('transfer quantity must be positive');
        if($expected===null || !isset($payload['to_expected_revision']) || filter_var($payload['to_expected_revision'],FILTER_VALIDATE_INT)===false || (int)$payload['to_expected_revision']<0) throw new InvalidArgumentException('transfer requires both expected revisions');
    }

    private function assertAuthorizedActor(string $actorId): void
    {
        $q=$this->db->prepare('SELECT username,role,enabled FROM app_users WHERE user_id=?');$q->execute([$actorId]);$actor=$q->fetch(PDO::FETCH_ASSOC);
        if(!$actor || (int)$actor['enabled']!==1 || $actor['role']!=='admin' || !hash_equals($this->approvedUsername,(string)$actor['username']))throw new DomainException('administrator_required');
    }

    /** @param array<string,mixed> $row @param array<string,mixed> $payload */
    private function lightOriginAuthorized(array $row,array $payload,string $now):bool
    {
        $kind=(string)($payload['_origin_kind']??'');$hash=(string)($payload['_origin_hash']??'');
        if(!in_array($kind,['web','mobile'],true)||!preg_match('/^[0-9a-f]{64}$/D',$hash))return false;
        $cutoff=DatabaseTime::from($now,-300);$userId=(string)$row['actor_id'];
        if($kind==='web'){
            $q=$this->db->prepare('SELECT created_at,expires_at,revoked_at,auth_method FROM web_sessions WHERE session_hash=? AND user_id=?');$q->execute([$hash,$userId]);$session=$q->fetch(PDO::FETCH_ASSOC);
            return (bool)$session&&$session['revoked_at']===null&&$session['auth_method']==='ha'&&(string)$session['created_at']>=$cutoff&&(string)$session['expires_at']>$now&&is_string($row['actor_last_ha_login_at'])&&(string)$row['actor_last_ha_login_at']>=$cutoff;
        }
        $q=$this->db->prepare("SELECT s.created_at,s.expires_at,s.revoked_at,c.capability FROM mobile_sessions s LEFT JOIN mobile_session_capabilities c ON c.token_hash=s.token_hash AND c.capability='light.control' WHERE s.token_hash=? AND s.user_id=?");$q->execute([$hash,$userId]);$session=$q->fetch(PDO::FETCH_ASSOC);
        return (bool)$session&&$session['revoked_at']===null&&$session['capability']==='light.control'&&(string)$session['created_at']>=$cutoff&&(string)$session['expires_at']>$now&&is_string($row['actor_last_ha_login_at'])&&(string)$row['actor_last_ha_login_at']>=$cutoff;
    }

    /** @param array<string,mixed> $details */
    private function audit(string $now,string $actor,string $action,string $type,string $id,array $details):void{$q=$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)');$q->execute([$now,$actor,$action,$type,$id,$this->json($details)]);}
    private function uuid(string $v):string{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$v))throw new InvalidArgumentException('invalid UUID');return strtolower($v);}
    /** @param mixed $v */ private function json($v):string{return json_encode($v,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);}
}
