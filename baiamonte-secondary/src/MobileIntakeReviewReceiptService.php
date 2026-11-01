<?php
declare(strict_types=1);

/** Source-disabled receipt store for one independently reviewed enology flow. */
final class MobileIntakeReviewReceiptService
{
    public const CONTRACT='baiamonte.mobile-intake-review.v1';
    /** @param array<string,string> $authorBinding @param array<string,array<string,mixed>> $reviewerBindings */
    public function __construct(private PDO $db,private array $authorBinding,private array $reviewerBindings)
    {
        $author=['website_user_id'=>strtolower(trim((string)($authorBinding['website_user_id']??''))),'website_username'=>mb_strtolower(trim((string)($authorBinding['website_username']??''))),'ha_user_id'=>strtolower(trim((string)($authorBinding['ha_user_id']??'')))];
        if(!$this->userUuid($author['website_user_id'])||$author['website_username']===''||!$this->haId($author['ha_user_id']))throw new InvalidArgumentException('explicit review author binding is required');
        $reviewers=[];foreach($reviewerBindings as $username=>$binding){$username=mb_strtolower(trim((string)$username));if($username===''||!is_array($binding))continue;$haId=strtolower(trim((string)($binding['ha_user_id']??'')));$role=trim((string)($binding['role']??''));$capabilities=array_values(array_filter(array_map(fn(mixed $value):string=>trim((string)$value),(array)($binding['capabilities']??[]))));if($this->haId($haId)&&$role!==''&&in_array('mobile_intake.enology.review',$capabilities,true))$reviewers[$username]=['ha_user_id'=>$haId,'role'=>$role];}
        if($reviewers===[])throw new InvalidArgumentException('explicit review reviewer policy is required');$this->authorBinding=$author;$this->reviewerBindings=$reviewers;
    }

    /** @param array<string,mixed> $decision */
    public function record(string $reportUuid,array $decision,string $now):void
    {
        $this->uuid($reportUuid);$now=DatabaseTime::from($now);$safe=$this->validate($reportUuid,$decision);
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT r.actor_id,r.actor_username,r.entry_kind,r.status,r.review_status,r.review_decision_uuid,r.review_decision_json,u.ha_user_id FROM mobile_intake_reports r JOIN app_users u ON u.user_id=r.actor_id WHERE r.report_uuid=?');$q->execute([$reportUuid]);$row=$q->fetch(PDO::FETCH_ASSOC);
            if(!$row||!hash_equals($this->authorBinding['website_user_id'],strtolower((string)$row['actor_id']))||!hash_equals($this->authorBinding['website_username'],mb_strtolower((string)$row['actor_username']))||!is_string($row['ha_user_id'])||!hash_equals($this->authorBinding['ha_user_id'],strtolower((string)$row['ha_user_id']))||(string)$row['entry_kind']!=='enology_reading'||(string)$row['status']!=='accepted')throw new DomainException('report outside initial review receipt scope');
            if($row['review_decision_uuid']!==null){$stored=json_decode((string)$row['review_decision_json'],true,32,JSON_THROW_ON_ERROR);if(!hash_equals((string)$row['review_decision_uuid'],$safe['decision_uuid'])||!is_array($stored)||!hash_equals($this->canonical($stored),$this->canonical($safe)))throw new DomainException('review decision collision');$this->db->commit();return;}
            $u=$this->db->prepare("UPDATE mobile_intake_reports SET review_status=?,review_revision=?,review_decision_uuid=?,review_decision_json=?,reviewed_by=?,reviewed_at=?,review_note=?,review_received_at=?,revision=revision+1,updated_at=? WHERE report_uuid=? AND review_status='pending_review' AND review_decision_uuid IS NULL");
            $u->execute([$safe['review_status'],$safe['review_revision'],$safe['decision_uuid'],$this->canonical($safe),$safe['reviewer']['username'],DatabaseTime::from($safe['reviewed_at']),$safe['review_note'],$now,$now,$reportUuid]);
            if($u->rowCount()!==1)throw new DomainException('review receipt state changed');
            $this->audit($now,$reportUuid,$safe);$this->db->commit();
        }catch(Throwable $error){if($this->db->inTransaction())$this->db->rollBack();throw $error;}
    }

    /** @return array<string,mixed> */
    public function status(string $reportUuid,string $actorId):array
    {
        $q=$this->db->prepare('SELECT review_status,review_revision,reviewed_by,reviewed_at,review_note,review_received_at FROM mobile_intake_reports WHERE report_uuid=? AND actor_id=?');$q->execute([$reportUuid,$actorId]);$row=$q->fetch(PDO::FETCH_ASSOC);if(!$row)throw new DomainException('intake report not found');
        return ['review_status'=>(string)$row['review_status'],'review_revision'=>$row['review_revision']===null?null:(string)$row['review_revision'],'reviewed_by'=>$row['reviewed_by'],'reviewed_at'=>$row['reviewed_at'],'review_note'=>$row['review_note'],'receipt_received_at'=>$row['review_received_at'],'business_application_status'=>'not_applied','domain_side_effects'=>[]];
    }

    /** @param array<string,mixed> $value @return array<string,mixed> */
    private function validate(string $reportUuid,array $value):array
    {
        if(($value['contract']??null)!==self::CONTRACT||($value['report_uuid']??null)!==$reportUuid||($value['business_application_status']??null)!=='not_applied'||($value['domain_side_effects']??null)!==[])throw new InvalidArgumentException('invalid review receipt contract');
        $decision=(string)($value['decision_uuid']??'');$this->uuid($decision);$status=(string)($value['review_status']??'');if(!in_array($status,['approved','rejected','correction_required'],true))throw new InvalidArgumentException('invalid review status');
        $revision=(string)($value['review_revision']??'');if(!preg_match('/^[1-9][0-9]{0,19}$/D',$revision))throw new InvalidArgumentException('invalid review revision');
        $reviewer=(array)($value['reviewer']??[]);$reviewerName=trim(mb_strtolower((string)($reviewer['username']??'')));$reviewerId=strtolower(trim((string)($reviewer['ha_user_id']??'')));$reviewerRole=(string)($reviewer['role']??'');$binding=$this->reviewerBindings[$reviewerName]??null;if(!is_array($binding)||!hash_equals((string)$binding['ha_user_id'],$reviewerId)||!hash_equals((string)$binding['role'],$reviewerRole)||hash_equals($this->authorBinding['ha_user_id'],$reviewerId))throw new DomainException('independent reviewer is not authorized');
        $note=trim((string)($value['review_note']??''));if($note===''||mb_strlen($note)>2000)throw new InvalidArgumentException('review note is required');
        $reviewed=DatabaseTime::from((string)($value['reviewed_at']??''));
        return ['contract'=>self::CONTRACT,'decision_uuid'=>strtolower($decision),'report_uuid'=>$reportUuid,'review_status'=>$status,'review_revision'=>$revision,'reviewed_at'=>str_replace(' ','T',$reviewed).'Z','review_note'=>$note,'reviewer'=>['username'=>$reviewerName,'ha_user_id'=>$reviewerId,'role'=>$reviewerRole],'business_application_status'=>'not_applied','domain_side_effects'=>[]];
    }
    /** @param array<string,mixed> $value */
    private function canonical(array $value):string{$sort=function(mixed $item)use(&$sort):mixed{if(!is_array($item))return $item;if($this->isList($item))return array_map($sort,$item);ksort($item,SORT_STRING);foreach($item as $key=>$child)$item[$key]=$sort($child);return $item;};return json_encode($sort($value),JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);}
    /** @param array<string,mixed> $value */
    private function audit(string $now,string $reportUuid,array $value):void{$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)')->execute([$now,'ha-review-sync','mobile.intake.review.received','mobile_intake_report',$reportUuid,$this->canonical($value)]);}
    private function uuid(string $value):void{if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value))throw new InvalidArgumentException('valid UUIDv4 is required');}
    private function userUuid(string $value):bool{return preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$value)===1;}
    private function haId(string $value):bool{return preg_match('/^[0-9a-f]{32}$/iD',$value)===1;}
    /** @param array<mixed> $value */
    private function isList(array $value):bool{$expected=0;foreach($value as $key=>$unused){if($key!==$expected++)return false;}return true;}
}
