<?php
declare(strict_types=1);

final class MobileIntakeService
{
    private PDO $db;
    private MobileFieldIntakeContract $contract;
    private string $privateDir;

    public function __construct(PDO $db,string $estateId,string $privateDir)
    {
        $privateDir=rtrim($privateDir,'/');
        if($privateDir===''||$privateDir[0]!=='/'||str_contains($privateDir,'/public_html'))throw new InvalidArgumentException('mobile intake requires an absolute non-public directory');
        if(!is_dir($privateDir)&&!mkdir($privateDir,0700,true)&&!is_dir($privateDir))throw new RuntimeException('mobile intake private directory is unavailable');
        if(!is_writable($privateDir))throw new RuntimeException('mobile intake private directory is not writable');
        @chmod($privateDir,0700);$this->db=$db;$this->contract=new MobileFieldIntakeContract($estateId);$this->privateDir=$privateDir;
    }

    /** @param array<string,mixed> $payload @param array<string,mixed> $actor @return array<string,mixed> */
    public function submit(array $payload,array $actor,string $now):array
    {
        $this->sweepExpiredAttachments($now);
        $normalized=$this->contract->validate($payload,$actor);$canonical=$this->canonical($normalized);$digest=hash('sha256',$canonical);$now=DatabaseTime::from($now);$uuid=(string)$normalized['report_uuid'];
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT actor_id,payload_sha256,status,revision FROM mobile_intake_reports WHERE report_uuid=?');$q->execute([$uuid]);$existing=$q->fetch(PDO::FETCH_ASSOC);
            if($existing){
                if(!hash_equals((string)$existing['actor_id'],(string)$actor['user_id'])||!hash_equals((string)$existing['payload_sha256'],$digest))throw new DomainException('report UUID content collision');
                $this->db->commit();return ['report_uuid'=>$uuid,'status'=>(string)$existing['status'],'revision'=>(string)$existing['revision'],'deduplicated'=>true];
            }
            $insert=$this->db->prepare('INSERT INTO mobile_intake_reports(report_uuid,estate_id,actor_id,actor_username,actor_role,entry_kind,occurred_at,client_created_at,received_at,source_timezone,payload_sha256,payload_json,status,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
            $insert->execute([$uuid,(string)$normalized['estate_id'],(string)$actor['user_id'],(string)$normalized['author']['username'],(string)$normalized['author']['server_role'],(string)$normalized['kind'],DatabaseTime::from((string)$normalized['occurred_at']),DatabaseTime::from((string)$normalized['client_created_at']),$now,(string)$normalized['source_timezone'],$digest,$canonical,'pending_review',1,$now,$now]);
            $this->audit($now,(string)$actor['user_id'],'mobile.intake.submitted',$uuid,['kind'=>$normalized['kind'],'payload_sha256'=>$digest]);$this->db->commit();
            return ['report_uuid'=>$uuid,'status'=>'pending_review','revision'=>'1','deduplicated'=>false];
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @param array<string,mixed> $actor @return array<string,mixed> */
    public function status(string $uuid,array $actor):array
    {
        $this->uuid($uuid);$q=$this->db->prepare('SELECT report_uuid,entry_kind,status,revision,received_at,updated_at,result_json FROM mobile_intake_reports WHERE report_uuid=? AND actor_id=?');$q->execute([$uuid,(string)$actor['user_id']]);$row=$q->fetch(PDO::FETCH_ASSOC);if(!$row)throw new DomainException('intake report not found');
        return ['report_uuid'=>(string)$row['report_uuid'],'kind'=>(string)$row['entry_kind'],'status'=>(string)$row['status'],'revision'=>(string)$row['revision'],'received_at'=>(string)$row['received_at'],'updated_at'=>(string)$row['updated_at'],'result'=>$row['result_json']===null?null:json_decode((string)$row['result_json'],true,32,JSON_THROW_ON_ERROR)];
    }

    /** @param array<string,mixed> $actor @return array<string,mixed> */
    public function uploadAttachment(string $reportUuid,array $actor,string $body,string $filename,string $now):array
    {
        $this->sweepExpiredAttachments($now);
        $this->uuid($reportUuid);$bytes=strlen($body);if($bytes<1||$bytes>15728640)throw new InvalidArgumentException('attachment must be between 1 byte and 15 MiB');
        $q=$this->db->prepare("SELECT payload_json,status FROM mobile_intake_reports WHERE report_uuid=? AND actor_id=?");$q->execute([$reportUuid,(string)$actor['user_id']]);$report=$q->fetch(PDO::FETCH_ASSOC);if(!$report)throw new DomainException('intake report not found');if(!in_array((string)$report['status'],['pending_review','leased'],true))throw new DomainException('intake report no longer accepts attachments');
        $digest=hash('sha256',$body);$finfo=new finfo(FILEINFO_MIME_TYPE);$mime=(string)$finfo->buffer($body);if(!in_array($mime,['image/jpeg','image/png','application/pdf'],true))throw new InvalidArgumentException('attachment type is not permitted');
        $payload=json_decode((string)$report['payload_json'],true,64,JSON_THROW_ON_ERROR);$matches=array_values(array_filter((array)($payload['attachments']??[]),fn(mixed $row):bool=>is_array($row)&&hash_equals((string)($row['sha256']??''),$digest)));$descriptor=$matches[0]??null;
        if(!is_array($descriptor)||!hash_equals((string)$descriptor['media_type'],$mime)||(int)$descriptor['byte_count']!==$bytes)throw new DomainException('attachment does not match its reserved descriptor');
        $existing=$this->db->prepare('SELECT attachment_uuid FROM mobile_intake_attachments WHERE report_uuid=? AND file_sha256=?');$existing->execute([$reportUuid,$digest]);$existingId=$existing->fetchColumn();if(is_string($existingId))return ['attachment_uuid'=>$existingId,'report_uuid'=>$reportUuid,'deduplicated'=>true];
        $attachmentUuid=$this->newUuid();$path=$this->privateDir.'/'.$attachmentUuid.'.bin';$temporary=$path.'.'.bin2hex(random_bytes(8)).'.tmp';
        if(file_put_contents($temporary,$body,LOCK_EX)!==$bytes){@unlink($temporary);throw new RuntimeException('attachment could not be stored');}@chmod($temporary,0600);if(!rename($temporary,$path)){@unlink($temporary);throw new RuntimeException('attachment could not be activated');}
        $now=DatabaseTime::from($now);$safeName=$filename===''?null:mb_substr(basename($filename),0,180);
        try{$this->db->beginTransaction();$insert=$this->db->prepare('INSERT INTO mobile_intake_attachments(attachment_uuid,report_uuid,file_sha256,media_type,byte_count,original_filename,stored_path,uploaded_at) VALUES(?,?,?,?,?,?,?,?)');$insert->execute([$attachmentUuid,$reportUuid,$digest,$mime,$bytes,$safeName,$path,$now]);$this->audit($now,(string)$actor['user_id'],'mobile.intake.attachment_uploaded',$reportUuid,['attachment_uuid'=>$attachmentUuid,'sha256'=>$digest,'byte_count'=>$bytes]);$this->db->commit();}
        catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();@unlink($path);throw $error;}
        return ['attachment_uuid'=>$attachmentUuid,'report_uuid'=>$reportUuid,'deduplicated'=>false];
    }

    /** @return list<array<string,mixed>> */
    public function lease(int $limit,string $now):array
    {
        $this->sweepExpiredAttachments($now);
        $limit=max(1,min(20,$limit));$now=DatabaseTime::from($now);$leaseUntil=DatabaseTime::from($now,90);$driver=$this->db->getAttribute(PDO::ATTR_DRIVER_NAME);$this->db->beginTransaction();
        try{
            $this->db->prepare("UPDATE mobile_intake_reports SET status='pending_review',lease_token_hash=NULL,lease_until=NULL,updated_at=? WHERE status='leased' AND lease_until<?")->execute([$now,$now]);
            $sql="SELECT report_uuid FROM mobile_intake_reports WHERE status='pending_review' ORDER BY received_at LIMIT ".$limit.($driver==='mysql'?' FOR UPDATE':'');$ids=$this->db->query($sql)->fetchAll(PDO::FETCH_COLUMN);if(!$ids){$this->db->commit();return [];}
            $claim=$this->db->prepare("UPDATE mobile_intake_reports SET status='leased',lease_token_hash=?,lease_until=?,delivery_attempts=delivery_attempts+1,revision=revision+1,updated_at=? WHERE report_uuid=? AND status='pending_review'");$rows=[];
            foreach($ids as $id){
                $q=$this->db->prepare('SELECT report_uuid,estate_id,actor_username,actor_role,entry_kind,payload_json,revision FROM mobile_intake_reports WHERE report_uuid=?');$q->execute([(string)$id]);$row=$q->fetch(PDO::FETCH_ASSOC);if(!$row)continue;
                $a=$this->db->prepare('SELECT attachment_uuid,file_sha256,media_type,byte_count FROM mobile_intake_attachments WHERE report_uuid=? AND deleted_at IS NULL ORDER BY uploaded_at');$a->execute([(string)$id]);$attachments=$a->fetchAll(PDO::FETCH_ASSOC);$payload=json_decode((string)$row['payload_json'],true,64,JSON_THROW_ON_ERROR);
                if(count($attachments)!==count((array)($payload['attachments']??[])))continue;
                $token=$this->randomToken();$tokenHash=hash('sha256',$token);
                $claim->execute([$tokenHash,$leaseUntil,$now,(string)$id]);if($claim->rowCount()!==1)continue;
                $rows[]=['report_uuid'=>(string)$row['report_uuid'],'estate_id'=>(string)$row['estate_id'],'actor'=>['username'=>(string)$row['actor_username'],'server_role'=>(string)$row['actor_role']],'kind'=>(string)$row['entry_kind'],'payload'=>$payload,'revision'=>(string)((int)$row['revision']+1),'lease_token'=>$token,'lease_until'=>$leaseUntil,'attachments'=>$attachments];
            }
            $this->db->commit();return $rows;
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @return array{path:string,media_type:string,byte_count:int} */
    public function leasedAttachment(string $reportUuid,string $attachmentUuid,string $leaseToken,string $now):array
    {
        $this->uuid($reportUuid);$this->uuid($attachmentUuid);$now=DatabaseTime::from($now);$q=$this->db->prepare("SELECT a.stored_path,a.media_type,a.byte_count FROM mobile_intake_attachments a JOIN mobile_intake_reports r ON r.report_uuid=a.report_uuid WHERE a.report_uuid=? AND a.attachment_uuid=? AND a.deleted_at IS NULL AND r.status='leased' AND r.lease_token_hash=? AND r.lease_until>=?");$q->execute([$reportUuid,$attachmentUuid,hash('sha256',$leaseToken),$now]);$row=$q->fetch(PDO::FETCH_ASSOC);if(!$row||!is_file((string)$row['stored_path']))throw new DomainException('leased attachment is unavailable');$this->db->prepare('UPDATE mobile_intake_attachments SET forwarded_at=? WHERE attachment_uuid=?')->execute([$now,$attachmentUuid]);return ['path'=>(string)$row['stored_path'],'media_type'=>(string)$row['media_type'],'byte_count'=>(int)$row['byte_count']];
    }

    /** @param array<string,mixed> $result */
    public function complete(string $reportUuid,string $leaseToken,string $status,array $result,string $now):void
    {
        $this->uuid($reportUuid);if(!in_array($status,['accepted','rejected','conflict'],true))throw new InvalidArgumentException('unsupported intake result status');$safe=$this->safeResult($result);$now=DatabaseTime::from($now);$this->db->beginTransaction();
        try{$q=$this->db->prepare("UPDATE mobile_intake_reports SET status=?,result_json=?,resolved_at=?,lease_token_hash=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE report_uuid=? AND status='leased' AND lease_token_hash=? AND lease_until>=?");$q->execute([$status,$this->canonical($safe),$now,$now,$reportUuid,hash('sha256',$leaseToken),$now]);if($q->rowCount()!==1)throw new DomainException('intake lease is stale or invalid');$this->audit($now,'ha-sync','mobile.intake.result',$reportUuid,['status'=>$status,'result'=>$safe]);$this->db->commit();}
        catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
        $this->deleteAcknowledgedAttachments($reportUuid,$now);
    }

    /** Hard-expire private website copies that HA has not acknowledged within 30 days. */
    public function sweepExpiredAttachments(string $now):int
    {
        $now=DatabaseTime::from($now);$cutoff=DatabaseTime::from($now,-2592000);$q=$this->db->prepare('SELECT attachment_uuid,report_uuid,stored_path FROM mobile_intake_attachments WHERE deleted_at IS NULL AND uploaded_at<?');$q->execute([$cutoff]);$count=0;
        foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){if(is_file((string)$row['stored_path'])&&!@unlink((string)$row['stored_path']))continue;$this->db->prepare('UPDATE mobile_intake_attachments SET deleted_at=? WHERE attachment_uuid=? AND deleted_at IS NULL')->execute([$now,(string)$row['attachment_uuid']]);$result=$this->canonical(['authoritative_record_ids'=>[],'actual_revisions'=>[],'reason'=>'attachment_retention_expired']);$this->db->prepare("UPDATE mobile_intake_reports SET status='rejected',result_json=?,resolved_at=?,lease_token_hash=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE report_uuid=? AND status IN ('pending_review','leased')")->execute([$result,$now,$now,(string)$row['report_uuid']]);$count++;}
        return $count;
    }

    /** @param array<string,mixed> $result @return array<string,mixed> */
    private function safeResult(array $result):array
    {
        $ids=[];foreach((array)($result['authoritative_record_ids']??[]) as $id){if(!is_string($id)||!preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$id))throw new InvalidArgumentException('invalid authoritative record id');$ids[]=$id;if(count($ids)>20)throw new InvalidArgumentException('too many authoritative record ids');}
        $revisions=[];foreach((array)($result['actual_revisions']??[]) as $key=>$revision){if(!is_string($key)||!is_string($revision)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new InvalidArgumentException('invalid result revision');$revisions[$key]=$revision;}
        $reason=$result['reason']??null;if($reason!==null&&!is_string($reason))throw new InvalidArgumentException('invalid intake result reason');return ['authoritative_record_ids'=>$ids,'actual_revisions'=>$revisions,'reason'=>$reason===null?null:mb_substr(trim($reason),0,1000)];
    }
    private function deleteAcknowledgedAttachments(string $reportUuid,string $now):void
    {
        $q=$this->db->prepare('SELECT attachment_uuid,stored_path FROM mobile_intake_attachments WHERE report_uuid=? AND deleted_at IS NULL');$q->execute([$reportUuid]);foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){if(is_file((string)$row['stored_path'])&&!@unlink((string)$row['stored_path']))continue;$this->db->prepare('UPDATE mobile_intake_attachments SET deleted_at=? WHERE attachment_uuid=? AND deleted_at IS NULL')->execute([$now,(string)$row['attachment_uuid']]);}
    }
    /** @param array<string,mixed> $value */
    private function canonical(array $value):string{$sort=function(mixed $item)use(&$sort):mixed{if(!is_array($item))return $item;if($this->isList($item))return array_map($sort,$item);ksort($item,SORT_STRING);foreach($item as $key=>$child)$item[$key]=$sort($child);return $item;};return json_encode($sort($value),JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);}
    /** @param array<string,mixed> $details */
    private function audit(string $now,string $actor,string $action,string $id,array $details):void{$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)')->execute([$now,$actor,$action,'mobile_intake_report',$id,json_encode($details,JSON_THROW_ON_ERROR)]);}
    private function uuid(string $value):void{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value))throw new InvalidArgumentException('valid UUIDv4 is required');}
    private function newUuid():string{$bytes=random_bytes(16);$bytes[6]=chr((ord($bytes[6])&0x0f)|0x40);$bytes[8]=chr((ord($bytes[8])&0x3f)|0x80);$hex=bin2hex($bytes);return substr($hex,0,8).'-'.substr($hex,8,4).'-'.substr($hex,12,4).'-'.substr($hex,16,4).'-'.substr($hex,20);}
    private function randomToken():string{return rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');}
    /** PHP 8.0-compatible equivalent of array_is_list(). @param array<mixed> $value */
    private function isList(array $value):bool{$expected=0;foreach($value as $key=>$unused){if($key!==$expected++)return false;}return true;}
}
