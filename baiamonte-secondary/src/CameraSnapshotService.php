<?php
declare(strict_types=1);

final class CameraSnapshotService
{
    private PDO $db;
    /** @var array<string,string> */
    private array $cameras;
    private string $approvedUsername;

    /** @param array<string,string> $cameras */
    public function __construct(PDO $db,array $cameras,string $approvedUsername)
    {
        $this->db=$db;
        $this->cameras=$cameras;
        $this->approvedUsername=$approvedUsername;
    }

    /** @return array<string,string> */
    public function catalog():array{return $this->cameras;}

    /** @param array<string,mixed> $user */
    public function create(array $user,string $cameraId,string $now):array
    {
        $now=DatabaseTime::from($now);
        $this->requireApprovedAdministrator($user);
        if(!array_key_exists($cameraId,$this->cameras))throw new InvalidArgumentException('camera_not_permitted');
        $this->sweep($now);
        $active=$this->db->prepare("SELECT request_uuid FROM camera_snapshot_requests WHERE actor_id=? AND camera_id=? AND status IN ('pending','leased','ready') AND expires_at>?");
        $active->execute([(string)$user['user_id'],$cameraId,$now]);
        if($existing=$active->fetchColumn())return ['request_uuid'=>(string)$existing,'status'=>'pending','deduplicated'=>true];
        $recent=$this->db->prepare('SELECT COUNT(*) FROM camera_snapshot_requests WHERE actor_id=? AND created_at>=?');
        $recent->execute([(string)$user['user_id'],DatabaseTime::from($now,-60)]);
        if((int)$recent->fetchColumn()>=6)throw new DomainException('camera_rate_limited');
        $global=$this->db->prepare("SELECT COUNT(*) FROM camera_snapshot_requests WHERE status IN ('pending','leased','ready') AND expires_at>?");
        $global->execute([$now]);
        if((int)$global->fetchColumn()>=1)throw new DomainException('camera_request_in_progress');
        $uuid=$this->uuid();$expires=DatabaseTime::from($now,45);
        $q=$this->db->prepare("INSERT INTO camera_snapshot_requests(request_uuid,camera_id,actor_id,status,created_at,expires_at) VALUES(?,?,?,'pending',?,?)");
        $q->execute([$uuid,$cameraId,(string)$user['user_id'],$now,$expires]);
        $this->audit($now,(string)$user['user_id'],'camera.snapshot.requested',$uuid,['camera_id'=>$cameraId]);
        return ['request_uuid'=>$uuid,'status'=>'pending','expires_at'=>$expires,'deduplicated'=>false];
    }

    /** @return list<array<string,mixed>> */
    public function lease(int $limit,string $now):array
    {
        $now=DatabaseTime::from($now);$this->sweep($now);$limit=1;$leaseUntil=DatabaseTime::from($now,15);
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare("SELECT request_uuid,camera_id,created_at,expires_at FROM camera_snapshot_requests WHERE status='pending' AND expires_at>? ORDER BY created_at LIMIT ".$limit);
            $q->execute([$now]);$rows=$q->fetchAll(PDO::FETCH_ASSOC);
            $u=$this->db->prepare("UPDATE camera_snapshot_requests SET status='leased',lease_until=? WHERE request_uuid=? AND status='pending'");
            $leased=[];
            foreach($rows as $row){$u->execute([$leaseUntil,$row['request_uuid']]);if($u->rowCount()===1)$leased[]=$row;}
            $this->db->commit();return $leased;
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    public function complete(string $uuid,string $cameraId,string $signedPath,string $issuedAt,string $expiresAt,string $now):void
    {
        $now=DatabaseTime::from($now);$issuedAt=DatabaseTime::from($issuedAt);$expiresAt=DatabaseTime::from($expiresAt);
        $this->sweep($now);$this->assertUuid($uuid);
        $q=$this->db->prepare("SELECT camera_id,status,expires_at FROM camera_snapshot_requests WHERE request_uuid=?");$q->execute([$uuid]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row||!in_array($row['status'],['pending','leased'],true))throw new DomainException('camera_request_not_active');
        if(!hash_equals((string)$row['camera_id'],$cameraId)||!array_key_exists($cameraId,$this->cameras))throw new DomainException('camera_request_mismatch');
        $issued=strtotime($issuedAt);$expires=strtotime($expiresAt);$clock=strtotime($now);
        if($issued===false||$expires===false||$clock===false||abs($clock-$issued)>10||$expires<=$clock||$expires-$issued>30)throw new InvalidArgumentException('invalid_signed_path_window');
        $parts=parse_url($signedPath);$expected='/api/camera_proxy/'.$cameraId;
        if(!is_array($parts)||isset($parts['scheme'])||isset($parts['host'])||($parts['path']??'')!==$expected||!isset($parts['query']))throw new InvalidArgumentException('invalid_signed_camera_path');
        parse_str((string)$parts['query'],$query);
        if(!is_string($query['authSig']??null)||strlen((string)$query['authSig'])<40||array_diff(array_keys($query),['authSig','width','height']))throw new InvalidArgumentException('invalid_signed_camera_query');
        $this->db->beginTransaction();
        try{
            $this->db->prepare('DELETE FROM camera_snapshot_tickets WHERE request_uuid=?')->execute([$uuid]);
            $this->db->prepare('INSERT INTO camera_snapshot_tickets(request_uuid,signed_path,expires_at) VALUES(?,?,?)')->execute([$uuid,$signedPath,$expiresAt]);
            $this->db->prepare("UPDATE camera_snapshot_requests SET status='ready',ready_at=?,expires_at=? WHERE request_uuid=?")->execute([$now,$expiresAt,$uuid]);
            $this->audit($now,'ha-camera','camera.snapshot.ready',$uuid,['camera_id'=>$cameraId,'expires_at'=>$expiresAt]);
            $this->db->commit();
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    public function fail(string $uuid,string $cameraId,string $reason,string $now):void
    {
        $now=DatabaseTime::from($now);
        $this->assertUuid($uuid);if(!array_key_exists($cameraId,$this->cameras))throw new InvalidArgumentException('camera_not_permitted');
        $reason=in_array($reason,['ha_offline','camera_unavailable','signing_failed','expired'],true)?$reason:'unavailable';
        $q=$this->db->prepare("UPDATE camera_snapshot_requests SET status='failed',failure_code=?,completed_at=? WHERE request_uuid=? AND camera_id=? AND status IN ('pending','leased')");
        $q->execute([$reason,$now,$uuid,$cameraId]);
        if($q->rowCount()===1)$this->audit($now,'ha-camera','camera.snapshot.failed',$uuid,['camera_id'=>$cameraId,'reason'=>$reason]);
    }

    /** @param array<string,mixed> $user */
    public function consume(array $user,string $uuid,string $now):array
    {
        $now=DatabaseTime::from($now);
        $this->requireApprovedAdministrator($user);$this->assertUuid($uuid);$this->sweep($now);
        $q=$this->db->prepare('SELECT camera_id,status,failure_code,expires_at FROM camera_snapshot_requests WHERE request_uuid=? AND actor_id=?');$q->execute([$uuid,(string)$user['user_id']]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row)throw new DomainException('camera_request_not_found');
        if($row['status']!=='ready')return ['status'=>(string)$row['status'],'camera_id'=>(string)$row['camera_id'],'failure_code'=>$row['failure_code'],'expires_at'=>(string)$row['expires_at']];
        $this->db->beginTransaction();
        try{
            $t=$this->db->prepare('SELECT signed_path,expires_at FROM camera_snapshot_tickets WHERE request_uuid=?');$t->execute([$uuid]);$ticket=$t->fetch(PDO::FETCH_ASSOC);
            if(!$ticket||strtotime((string)$ticket['expires_at'])<=strtotime($now)){throw new DomainException('camera_ticket_expired');}
            $this->db->prepare('DELETE FROM camera_snapshot_tickets WHERE request_uuid=?')->execute([$uuid]);
            $this->db->prepare("UPDATE camera_snapshot_requests SET status='consumed',completed_at=? WHERE request_uuid=? AND status='ready'")->execute([$now,$uuid]);
            $this->audit($now,(string)$user['user_id'],'camera.snapshot.consumed',$uuid,['camera_id'=>$row['camera_id']]);
            $this->db->commit();
            return ['status'=>'ready','camera_id'=>(string)$row['camera_id'],'signed_path'=>(string)$ticket['signed_path'],'expires_at'=>(string)$ticket['expires_at']];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    public function sweep(string $now):void
    {
        $now=DatabaseTime::from($now);
        $this->db->prepare('DELETE FROM camera_snapshot_tickets WHERE expires_at<=?')->execute([$now]);
        $this->db->prepare("UPDATE camera_snapshot_requests SET status='pending',lease_until=NULL WHERE status='leased' AND lease_until<=? AND expires_at>?")->execute([$now,$now]);
        $this->db->prepare("UPDATE camera_snapshot_requests SET status='expired',completed_at=? WHERE status IN ('pending','leased','ready') AND expires_at<=?")->execute([$now,$now]);
    }

    /** @param array<string,mixed> $user */
    private function requireApprovedAdministrator(array $user):void
    {
        if(!hash_equals($this->approvedUsername,(string)($user['username']??''))||($user['role']??'')!=='admin')throw new DomainException('camera_access_denied');
    }
    private function assertUuid(string $uuid):void{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$uuid))throw new InvalidArgumentException('invalid_camera_request_id');}
    private function uuid():string{$b=random_bytes(16);$b[6]=chr((ord($b[6])&15)|64);$b[8]=chr((ord($b[8])&63)|128);$h=bin2hex($b);return substr($h,0,8).'-'.substr($h,8,4).'-'.substr($h,12,4).'-'.substr($h,16,4).'-'.substr($h,20);}
    private function audit(string $now,string $actor,string $action,string $id,array $details):void{$q=$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)');$q->execute([$now,$actor,$action,'camera_snapshot',$id,json_encode($details,JSON_THROW_ON_ERROR)]);}
}
