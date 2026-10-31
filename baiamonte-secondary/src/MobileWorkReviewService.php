<?php
declare(strict_types=1);

final class MobileWorkReviewConflict extends DomainException {}
final class MobileWorkReviewForbidden extends DomainException {}
final class MobileWorkReviewRequestError extends InvalidArgumentException {}

final class MobileWorkReviewService
{
    public const CONTRACT='baiamonte.mobile-work-review.v1';

    private ReplicaService $replica;
    private string $estateId;

    /** @var array<string,array<string,array{object:string,roles:list<string>,fields:list<string>}>> */
    private const DATASETS=[
        'work'=>[
            'tasks'=>[
                'object'=>'tasks','roles'=>['operator','admin'],
                'fields'=>['title','status','priority','due_date','completed_at','category','block_id','season_id','estimated_hours'],
            ],
            'activities'=>[
                'object'=>'work_activities','roles'=>['operator','admin'],
                'fields'=>['title','status','category','activity_date','end_date','block_id','task_id','season_id','labor_hours','worker_count'],
            ],
            'open'=>[
                'object'=>'v_open_work','roles'=>['operator','admin'],
                'fields'=>['title','status','priority','due_date','days_until_due','category','block_code','block_name'],
            ],
            'issues'=>[
                'object'=>'issues_decisions','roles'=>['operator','admin'],
                'fields'=>['issue_text','issue_type','subject_ref','status','priority','opened_date','due_date','closed_date','decision_action'],
            ],
        ],
        'review'=>[
            'queue'=>[
                'object'=>'ro_lab_decision_queue','roles'=>['admin'],
                'fields'=>['sample_id','sample_name','sample_type','lab_date','result_count','flagged_results','needs_review','review_status','next_check_at'],
            ],
            'history'=>[
                'object'=>'lab_reviews','roles'=>['admin'],
                'fields'=>['sample_id','decision_type','review_status','decision_action','interpretation','enologist_approval_required','approved_at','next_check_at','created_at','updated_at'],
            ],
        ],
    ];

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=strtolower($estateId);
    }

    /** @param array<string,mixed> $query @return array<string,mixed> */
    public function page(string $view,string $role,array $query,string $now):array
    {
        if(!isset(self::DATASETS[$view]))throw new MobileWorkReviewRequestError('unsupported mobile view');
        $this->validateQueryKeys($query);
        $dataset=is_string($query['dataset']??null)?(string)$query['dataset']:'';
        if(!isset(self::DATASETS[$view][$dataset]))throw new MobileWorkReviewRequestError('unsupported mobile dataset');
        $definition=self::DATASETS[$view][$dataset];
        if(!in_array($role,$definition['roles'],true))throw new MobileWorkReviewForbidden('mobile role is not permitted');
        $state=is_string($query['state']??null)?(string)$query['state']:($view==='work'?'open':'pending');
        if(!in_array($state,['all','open','completed','pending'],true)||($view==='work'&&$state==='pending')||($view==='review'&&$state==='open'))throw new MobileWorkReviewRequestError('unsupported mobile state filter');
        $limit=$this->limit($query['limit']??50);
        $cursor=is_string($query['cursor']??null)?(string)$query['cursor']:'';
        if(strlen($cursor)>512)throw new MobileWorkReviewRequestError('invalid mobile cursor');

        $before=$this->replica->status($now);$snapshot=(string)($before['active_snapshot_id']??'');$generation=$snapshot===''?'':hash('sha256',$snapshot);$anchor='';
        if($cursor!==''){
            $decoded=$this->decodeCursor($cursor);
            if(!hash_equals($view,(string)$decoded['v'])||!hash_equals($dataset,(string)$decoded['d'])||!hash_equals($state,(string)$decoded['s']))throw new MobileWorkReviewRequestError('mobile cursor does not match request');
            if($generation===''||!hash_equals($generation,(string)$decoded['g']))throw new MobileWorkReviewConflict('mobile replica snapshot changed');
            $anchor=(string)$decoded['a'];
        }

        $items=[];$hasMore=false;$object=$definition['object'];$available=$snapshot!==''&&$this->replica->permitsObject($object);
        if($available){
            $records=$this->replica->records($object);
            usort($records,fn(array $left,array $right):int=>strcmp((string)($left['id']??''),(string)($right['id']??'')));
            foreach($records as $record){
                $id=(string)($record['id']??'');if($anchor!==''&&strcmp($id,$anchor)<=0)continue;
                $data=is_array($record['data']??null)?$record['data']:[];
                if(!is_string($data['estate_id']??null)||!hash_equals($this->estateId,strtolower((string)$data['estate_id'])))continue;
                if(!$this->matchesState($view,$state,$data))continue;
                if(count($items)===$limit){$hasMore=true;break;}
                $items[]=$this->item($id,(string)($record['revision']??''),$record['source_updated_at']??null,$data,$definition['fields']);
            }
        }

        $after=$this->replica->status($now);
        if((string)($after['active_snapshot_id']??'')!==$snapshot)throw new MobileWorkReviewConflict('mobile replica snapshot changed');
        $next=$hasMore&&$items?$this->encodeCursor($generation,$view,$dataset,$state,(string)$items[count($items)-1]['id']):null;
        return [
            'contract'=>self::CONTRACT,'view'=>$view,'dataset'=>$dataset,'estate_id'=>$this->estateId,
            'source'=>[
                'source_generated_at'=>$after['source_generated_at']??null,'last_success_at'=>$after['last_success_at']??null,
                'data_age_seconds'=>$after['data_age_seconds']??null,'state'=>$snapshot===''?'unavailable':(($after['last_error']??null)===null?'ready':'degraded'),
            ],
            'available'=>$available,'filters'=>['state'=>$state],'items'=>$items,'next_cursor'=>$next,
        ];
    }

    /** @param array<string,mixed> $query */
    private function validateQueryKeys(array $query):void
    {
        foreach(array_keys($query) as $key)if(!in_array((string)$key,['dataset','state','limit','cursor'],true))throw new MobileWorkReviewRequestError('unsupported mobile filter');
        foreach(['dataset','state','cursor'] as $key)if(isset($query[$key])&&!is_string($query[$key]))throw new MobileWorkReviewRequestError('invalid mobile filter');
    }

    private function limit(mixed $value):int
    {
        if(is_string($value)&&!preg_match('/^[0-9]{1,3}$/D',$value))throw new MobileWorkReviewRequestError('invalid mobile limit');
        if(!is_int($value)&&!is_string($value))throw new MobileWorkReviewRequestError('invalid mobile limit');
        $limit=filter_var($value,FILTER_VALIDATE_INT);
        if($limit===false||$limit<1||$limit>100)throw new MobileWorkReviewRequestError('mobile limit must be between 1 and 100');
        return $limit;
    }

    /** @param array<string,mixed> $data */
    private function matchesState(string $view,string $state,array $data):bool
    {
        if($state==='all')return true;
        if($view==='work'){
            $status=strtolower(trim(is_string($data['status']??null)?(string)$data['status']:''));
            $terminal=in_array($status,['done','completed','closed','resolved','cancelled','rejected','superseded'],true);
            return $state==='completed'?$terminal:!$terminal;
        }
        $needsReview=filter_var($data['needs_review']??false,FILTER_VALIDATE_BOOL,FILTER_NULL_ON_FAILURE)===true;
        $status=strtolower(trim(is_string($data['review_status']??null)?(string)$data['review_status']:''));
        $pending=$needsReview||in_array($status,['','unreviewed','pending','pending_review','review_required','needs_review'],true);
        return $state==='pending'?$pending:!$pending;
    }

    /** @param list<string> $fields @param array<string,mixed> $data @return array<string,mixed> */
    private function item(string $id,string $revision,mixed $sourceUpdatedAt,array $data,array $fields):array
    {
        if(!$this->validId($id)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new DomainException('invalid mobile replica record');
        $safe=[];
        foreach($fields as $field){
            if(!array_key_exists($field,$data)||$data[$field]===null)continue;$value=$data[$field];
            if(is_string($value)){$value=trim($value);if($value==='')continue;$safe[$field]=mb_substr($value,0,in_array($field,['issue_text','decision_action','interpretation'],true)?500:160);}
            elseif(is_int($value)||is_float($value)||is_bool($value))$safe[$field]=$value;
        }
        return ['id'=>$id,'revision'=>$revision,'source_updated_at'=>is_string($sourceUpdatedAt)?$sourceUpdatedAt:null,'data'=>$safe];
    }

    /** @return array{g:string,v:string,d:string,s:string,a:string} */
    private function decodeCursor(string $cursor):array
    {
        if(!preg_match('/^[A-Za-z0-9_-]+$/D',$cursor))throw new MobileWorkReviewRequestError('invalid mobile cursor');
        $raw=base64_decode(strtr($cursor,'-_','+/').str_repeat('=',(4-strlen($cursor)%4)%4),true);
        if($raw===false)throw new MobileWorkReviewRequestError('invalid mobile cursor');
        try{$value=json_decode($raw,true,8,JSON_THROW_ON_ERROR);}catch(JsonException $error){throw new MobileWorkReviewRequestError('invalid mobile cursor',0,$error);}
        if(!is_array($value)||($value['c']??null)!==1||!is_string($value['g']??null)||!preg_match('/^[0-9a-f]{64}$/D',(string)$value['g'])||!is_string($value['v']??null)||!is_string($value['d']??null)||!is_string($value['s']??null)||!is_string($value['a']??null)||!$this->validId((string)$value['a']))throw new MobileWorkReviewRequestError('invalid mobile cursor');
        return ['g'=>$value['g'],'v'=>$value['v'],'d'=>$value['d'],'s'=>$value['s'],'a'=>$value['a']];
    }

    private function encodeCursor(string $generation,string $view,string $dataset,string $state,string $anchor):string
    {
        $raw=json_encode(['c'=>1,'g'=>$generation,'v'=>$view,'d'=>$dataset,'s'=>$state,'a'=>$anchor],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
        return rtrim(strtr(base64_encode($raw),'+/','-_'),'=');
    }

    private function validId(string $value):bool{return (bool)preg_match('/^[A-Za-z0-9][A-Za-z0-9._:|\-]{0,190}$/D',$value);}
}
