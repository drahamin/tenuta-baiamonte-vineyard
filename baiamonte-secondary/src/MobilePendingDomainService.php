<?php
declare(strict_types=1);

/**
 * Disabled durable mailbox for validated timeclock/cellar domain requests.
 *
 * It persists immutable requests and authoritative results only. It never
 * changes source tables, inventory, shifts, payroll, equipment or replicas.
 */
final class MobilePendingDomainService
{
    public const CONTRACT='baiamonte.mobile-pending-domain.v1';
    private const CAPABILITIES=['timeclock'=>'timeclock.submit','cellar'=>'cellar.operations.submit'];
    private PDO $db;
    private MobileTimeclockContract $timeclock;
    private MobileCellarOperationContract $cellar;

    public function __construct(PDO $db,string $estateId)
    {
        $this->db=$db;$this->timeclock=new MobileTimeclockContract($estateId);$this->cellar=new MobileCellarOperationContract($estateId);
    }

    /** @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function submitTimeclock(array $payload,array $actor,string $now):array{return $this->submit('timeclock',$this->timeclock->validate($payload,$actor),$actor,$now);}
    /** @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function submitCellar(array $payload,array $actor,string $now):array{return $this->submit('cellar',$this->cellar->validate($payload,$actor),$actor,$now);}

    /** @param array<string,mixed> $actor @return array<string,mixed> */
    private function submit(string $workflow,array $normalized,array $actor,string $now):array
    {
        $capability=self::CAPABILITIES[$workflow];$tokenHash=(string)($actor['token_hash']??'');
        if(!preg_match('/^[0-9a-f]{64}$/D',$tokenHash)||!in_array($capability,(array)($actor['capabilities']??[]),true))throw new DomainException('current '.$workflow.' capability is required');
        $now=DatabaseTime::from($now);$this->assertCurrentAuthority($tokenHash,(string)($actor['user_id']??''),(string)($actor['username']??''),(string)($actor['role']??''),$capability,$now);
        $uuid=(string)($normalized[$workflow==='timeclock'?'event_uuid':'operation_uuid']??'');$canonical=$this->canonical($normalized);$digest=hash('sha256',$canonical);
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT actor_id,payload_sha256,status,revision FROM mobile_pending_domain_actions WHERE action_uuid=?');$q->execute([$uuid]);$existing=$q->fetch(PDO::FETCH_ASSOC);
            if($existing){if(!hash_equals((string)$existing['actor_id'],(string)$actor['user_id'])||!hash_equals((string)$existing['payload_sha256'],$digest))throw new DomainException('domain action UUID content collision');$this->db->commit();return ['action_uuid'=>$uuid,'workflow'=>$workflow,'status'=>(string)$existing['status'],'revision'=>(string)$existing['revision'],'deduplicated'=>true];}
            $insert=$this->db->prepare('INSERT INTO mobile_pending_domain_actions(action_uuid,workflow,estate_id,actor_id,actor_username,actor_role,origin_token_hash,required_capability,payload_sha256,payload_json,status,revision,received_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
            $insert->execute([$uuid,$workflow,(string)$normalized['estate_id'],(string)$actor['user_id'],(string)$actor['username'],(string)$actor['role'],$tokenHash,$capability,$digest,$canonical,'pending_validation',1,$now,$now,$now]);
            $this->audit($now,(string)$actor['user_id'],'mobile.domain.submitted',$uuid,['workflow'=>$workflow,'payload_sha256'=>$digest]);$this->db->commit();
            return ['action_uuid'=>$uuid,'workflow'=>$workflow,'status'=>'pending_validation','revision'=>'1','deduplicated'=>false];
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @return array<string,mixed> */
    public function status(string $uuid,array $actor):array
    {
        $this->uuid($uuid);$q=$this->db->prepare('SELECT action_uuid,workflow,status,revision,received_at,updated_at,result_json FROM mobile_pending_domain_actions WHERE action_uuid=? AND actor_id=?');$q->execute([$uuid,(string)($actor['user_id']??'')]);$row=$q->fetch(PDO::FETCH_ASSOC);if(!$row)throw new DomainException('domain action not found');
        return ['contract'=>self::CONTRACT,'action_uuid'=>(string)$row['action_uuid'],'workflow'=>(string)$row['workflow'],'status'=>(string)$row['status'],'revision'=>(string)$row['revision'],'received_at'=>(string)$row['received_at'],'updated_at'=>(string)$row['updated_at'],'result'=>$row['result_json']===null?null:json_decode((string)$row['result_json'],true,32,JSON_THROW_ON_ERROR)];
    }

    /** @return list<array<string,mixed>> */
    public function lease(int $limit,string $now):array
    {
        $limit=max(1,min(20,$limit));$now=DatabaseTime::from($now);$leaseUntil=DatabaseTime::from($now,90);$driver=$this->db->getAttribute(PDO::ATTR_DRIVER_NAME);$this->rejectInvalidAuthority($now);$this->db->beginTransaction();
        try{
            $this->db->prepare("UPDATE mobile_pending_domain_actions SET status='pending_validation',lease_token_hash=NULL,lease_until=NULL,updated_at=? WHERE status='leased' AND lease_until<?")->execute([$now,$now]);
            $sql="SELECT a.action_uuid,a.workflow,a.estate_id,a.actor_username,a.actor_role,a.required_capability,a.payload_json,a.revision FROM mobile_pending_domain_actions a JOIN app_users u ON u.user_id=a.actor_id JOIN mobile_sessions s ON s.token_hash=a.origin_token_hash JOIN mobile_domain_session_capabilities c ON c.token_hash=s.token_hash AND c.capability=a.required_capability WHERE a.status='pending_validation' AND u.enabled=1 AND u.role=a.actor_role AND s.revoked_at IS NULL AND s.expires_at>=? ORDER BY a.received_at,a.action_uuid LIMIT ".$limit.($driver==='mysql'?' FOR UPDATE':'');
            $q=$this->db->prepare($sql);$q->execute([$now]);$claim=$this->db->prepare("UPDATE mobile_pending_domain_actions SET status='leased',lease_token_hash=?,lease_until=?,delivery_attempts=delivery_attempts+1,revision=revision+1,updated_at=? WHERE action_uuid=? AND status='pending_validation'");$rows=[];
            foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){$token=$this->token();$claim->execute([hash('sha256',$token),$leaseUntil,$now,(string)$row['action_uuid']]);if($claim->rowCount()!==1)continue;$rows[]=['contract'=>self::CONTRACT,'action_uuid'=>(string)$row['action_uuid'],'workflow'=>(string)$row['workflow'],'authoritative_handler'=>$row['workflow']==='timeclock'?'vineyard.timeclock.record_event.v1':'vineyard.cellar.apply_operation.v1','estate_id'=>(string)$row['estate_id'],'actor'=>['username'=>(string)$row['actor_username'],'server_role'=>(string)$row['actor_role']],'authority'=>['capability'=>(string)$row['required_capability'],'session_active'=>true,'checked_at'=>gmdate('Y-m-d\TH:i:s\Z',strtotime($now))],'payload'=>json_decode((string)$row['payload_json'],true,64,JSON_THROW_ON_ERROR),'revision'=>(string)((int)$row['revision']+1),'lease_token'=>$token,'lease_until'=>$leaseUntil];}
            $this->db->commit();return $rows;
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @param array<string,mixed> $result */
    public function complete(string $uuid,string $leaseToken,string $status,array $result,string $now):void
    {
        $this->uuid($uuid);if(!in_array($status,['accepted','rejected','conflict'],true))throw new InvalidArgumentException('unsupported domain result status');$now=DatabaseTime::from($now);$this->db->beginTransaction();
        try{
            $read=$this->db->prepare('SELECT workflow FROM mobile_pending_domain_actions WHERE action_uuid=? AND status=\'leased\' AND lease_token_hash=? AND lease_until>=?');$read->execute([$uuid,hash('sha256',$leaseToken),$now]);$workflow=$read->fetchColumn();if(!is_string($workflow))throw new DomainException('domain action lease is stale or invalid');$safe=$this->result($workflow,$status,$result);
            if($status==='accepted'&&!$this->authorityStillValid($uuid,$now)){$status='rejected';$safe=['authoritative_record_ids'=>[],'actual_revisions'=>[],'reason'=>'authority_revoked_before_acknowledgement','transaction_uuid'=>null,'inventory_committed'=>false,'atomic'=>false];}
            $q=$this->db->prepare("UPDATE mobile_pending_domain_actions SET status=?,result_json=?,resolved_at=?,lease_token_hash=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE action_uuid=? AND status='leased' AND lease_token_hash=? AND lease_until>=?");$q->execute([$status,$this->canonical($safe),$now,$now,$uuid,hash('sha256',$leaseToken),$now]);if($q->rowCount()!==1)throw new DomainException('domain action lease is stale or invalid');$this->audit($now,'ha-sync','mobile.domain.result',$uuid,['workflow'=>$workflow,'status'=>$status,'result'=>$safe]);$this->db->commit();
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @param array<string,mixed> $result @return array<string,mixed> */
    private function result(string $workflow,string $status,array $result):array
    {
        foreach(array_keys($result) as $key)if(!in_array((string)$key,['authoritative_record_ids','actual_revisions','reason','transaction_uuid','inventory_committed','atomic'],true))throw new InvalidArgumentException('unsupported domain result field');
        $ids=[];foreach((array)($result['authoritative_record_ids']??[]) as $id){if(!is_string($id)||!preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$id))throw new InvalidArgumentException('invalid authoritative record id');$ids[]=$id;if(count($ids)>20)throw new InvalidArgumentException('too many authoritative record ids');}
        $revisions=[];foreach((array)($result['actual_revisions']??[]) as $key=>$revision){if(!is_string($key)||!is_string($revision)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new InvalidArgumentException('invalid result revision');$revisions[$key]=$revision;}
        $reason=$result['reason']??null;if($reason!==null&&!is_string($reason))throw new InvalidArgumentException('invalid domain result reason');$transaction=$result['transaction_uuid']??null;if($transaction!==null)$this->uuid((string)$transaction);
        $inventory=($result['inventory_committed']??false)===true;$atomic=($result['atomic']??false)===true;
        if($status==='accepted'&&(!$ids||!$revisions))throw new InvalidArgumentException('accepted domain result requires authoritative ids and revisions');
        if($status==='accepted'&&$workflow==='cellar'&&($transaction===null||!$inventory||!$atomic))throw new InvalidArgumentException('accepted cellar result requires one atomic inventory transaction');
        if($workflow==='timeclock'&&($transaction!==null||$inventory||$atomic))throw new InvalidArgumentException('timeclock result cannot claim an inventory transaction');
        return ['authoritative_record_ids'=>$ids,'actual_revisions'=>$revisions,'reason'=>$reason===null?null:mb_substr(trim($reason),0,1000),'transaction_uuid'=>$transaction===null?null:strtolower((string)$transaction),'inventory_committed'=>$inventory,'atomic'=>$atomic];
    }

    private function rejectInvalidAuthority(string $now):void
    {
        $sql="SELECT a.action_uuid,CASE WHEN u.enabled<>1 THEN 'authority_disabled' WHEN u.role<>a.actor_role THEN 'authority_role_changed' WHEN s.revoked_at IS NOT NULL OR s.expires_at<? THEN 'authority_session_inactive' WHEN c.capability IS NULL THEN 'authority_capability_revoked' ELSE NULL END reason FROM mobile_pending_domain_actions a JOIN app_users u ON u.user_id=a.actor_id JOIN mobile_sessions s ON s.token_hash=a.origin_token_hash LEFT JOIN mobile_domain_session_capabilities c ON c.token_hash=s.token_hash AND c.capability=a.required_capability WHERE a.status='pending_validation'";$q=$this->db->prepare($sql);$q->execute([$now]);foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row)if(is_string($row['reason']))$this->db->prepare("UPDATE mobile_pending_domain_actions SET status='rejected',result_json=?,resolved_at=?,revision=revision+1,updated_at=? WHERE action_uuid=? AND status='pending_validation'")->execute([$this->canonical(['authoritative_record_ids'=>[],'actual_revisions'=>[],'reason'=>$row['reason'],'transaction_uuid'=>null,'inventory_committed'=>false,'atomic'=>false]),$now,$now,(string)$row['action_uuid']]);
    }
    private function authorityStillValid(string $uuid,string $now):bool{$q=$this->db->prepare('SELECT COUNT(*) FROM mobile_pending_domain_actions a JOIN app_users u ON u.user_id=a.actor_id JOIN mobile_sessions s ON s.token_hash=a.origin_token_hash JOIN mobile_domain_session_capabilities c ON c.token_hash=s.token_hash AND c.capability=a.required_capability WHERE a.action_uuid=? AND u.enabled=1 AND u.role=a.actor_role AND s.revoked_at IS NULL AND s.expires_at>=?');$q->execute([$uuid,$now]);return (int)$q->fetchColumn()===1;}
    private function assertCurrentAuthority(string $tokenHash,string $userId,string $username,string $role,string $capability,string $now):void{$q=$this->db->prepare('SELECT COUNT(*) FROM app_users u JOIN mobile_sessions s ON s.user_id=u.user_id JOIN mobile_domain_session_capabilities c ON c.token_hash=s.token_hash WHERE s.token_hash=? AND u.user_id=? AND u.username=? AND u.role=? AND u.enabled=1 AND s.revoked_at IS NULL AND s.expires_at>=? AND c.capability=?');$q->execute([$tokenHash,$userId,$username,$role,$now,$capability]);if((int)$q->fetchColumn()!==1)throw new DomainException('current domain authority is required');}
    /** @param array<string,mixed> $details */
    private function audit(string $now,string $actor,string $action,string $uuid,array $details):void{$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)')->execute([$now,$actor,$action,'mobile_domain_action',$uuid,json_encode($details,JSON_THROW_ON_ERROR)]);}
    /** @param array<string,mixed> $value */
    private function canonical(array $value):string{$sort=function(mixed $item)use(&$sort):mixed{if(!is_array($item))return $item;if($this->isList($item))return array_map($sort,$item);ksort($item,SORT_STRING);foreach($item as $key=>$child)$item[$key]=$sort($child);return $item;};return json_encode($sort($value),JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);}
    private function uuid(string $value):void{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value))throw new InvalidArgumentException('valid UUIDv4 is required');}
    private function token():string{return rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');}
    /** @param array<mixed> $value */
    private function isList(array $value):bool{$expected=0;foreach($value as $key=>$unused)if($key!==$expected++)return false;return true;}
}
