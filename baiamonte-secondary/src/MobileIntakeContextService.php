<?php
declare(strict_types=1);

final class MobileIntakeContextConflict extends DomainException {}

final class MobileIntakeContextService
{
    private ReplicaService $replica;
    private string $estateId;

    /** @var array<string,string> */
    private const OBJECTS=[
        'block_id'=>'vineyard_blocks',
        'task_id'=>'tasks',
        'work_activity_id'=>'work_activities',
        'container_id'=>'cellar_containers',
        'wine_lot_id'=>'wine_lots',
    ];
    /** @var array<string,list<string>> */
    private const LABEL_FIELDS=[
        'block_id'=>['code','name'],
        'task_id'=>['title'],
        'work_activity_id'=>['title','activity_type'],
        'container_id'=>['code','name'],
        'wine_lot_id'=>['code','name'],
    ];
    /** @var array<string,list<string>> */
    private const RELATIONS=[
        'task_id'=>['block_id'],
        'work_activity_id'=>['block_id'],
        'wine_lot_id'=>['current_container_id'],
    ];

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=strtolower($estateId);
    }

    /** @return array<string,mixed> */
    public function page(string $role,string $entityType,int $limit,string $cursor,string $now):array
    {
        if(!in_array($role,['operator','admin'],true))throw new DomainException('mobile intake context role is not permitted');
        if(!isset(self::OBJECTS[$entityType]))throw new InvalidArgumentException('unsupported intake entity type');
        if($limit<1||$limit>100)throw new InvalidArgumentException('context limit must be between 1 and 100');
        if(strlen($cursor)>512)throw new InvalidArgumentException('invalid intake context cursor');
        $before=$this->replica->status($now);$snapshot=(string)($before['active_snapshot_id']??'');$generation=$snapshot===''?'':hash('sha256',$snapshot);
        $anchor='';
        if($cursor!==''){
            $decoded=$this->decodeCursor($cursor);
            if(!hash_equals($entityType,(string)($decoded['t']??'')))throw new InvalidArgumentException('intake context cursor does not match entity type');
            if($generation===''||!hash_equals($generation,(string)($decoded['g']??'')))throw new MobileIntakeContextConflict('intake context snapshot changed');
            $anchor=(string)($decoded['a']??'');
            if(!$this->validId($anchor))throw new InvalidArgumentException('invalid intake context cursor');
        }
        $items=[];$hasMore=false;$available=$snapshot!==''&&$this->replica->permitsObject(self::OBJECTS[$entityType]);
        if($available){
            $records=$this->replica->records(self::OBJECTS[$entityType]);
            usort($records,fn(array $left,array $right):int=>strcmp((string)($left['id']??''),(string)($right['id']??'')));
            foreach($records as $record){
                $id=(string)($record['id']??'');
                if($anchor!==''&&strcmp($id,$anchor)<=0)continue;
                $data=is_array($record['data']??null)?$record['data']:[];
                if(!is_string($data['estate_id']??null)||!hash_equals($this->estateId,strtolower((string)$data['estate_id'])))continue;
                if(count($items)===$limit){$hasMore=true;break;}
                $items[]=$this->item($entityType,$id,(string)($record['revision']??''),$data);
            }
        }
        $after=$this->replica->status($now);
        if((string)($after['active_snapshot_id']??'')!==$snapshot)throw new MobileIntakeContextConflict('intake context snapshot changed');
        $source=[
            'source_generated_at'=>$after['source_generated_at']??null,
            'last_success_at'=>$after['last_success_at']??null,
            'data_age_seconds'=>$after['data_age_seconds']??null,
            'state'=>$snapshot===''?'unavailable':(($after['last_error']??null)===null?'ready':'degraded'),
        ];
        $next=null;
        if($hasMore&&$items)$next=$this->encodeCursor($generation,$entityType,(string)$items[count($items)-1]['id']);
        return ['context_version'=>1,'estate_id'=>$this->estateId,'source'=>$source,'entity_type'=>$entityType,'available'=>$available,'items'=>$items,'next_cursor'=>$next];
    }

    /** @param array<string,mixed> $data @return array<string,mixed> */
    private function item(string $entityType,string $id,string $revision,array $data):array
    {
        if(!$this->validId($id)||!preg_match('/^(0|[1-9][0-9]{0,19})$/D',$revision))throw new DomainException('invalid authoritative intake context record');
        $label=$id;
        foreach(self::LABEL_FIELDS[$entityType] as $field){$value=$data[$field]??null;if(is_string($value)&&trim($value)!==''){$label=mb_substr(trim($value),0,160);break;}}
        $status=null;
        if(is_string($data['status']??null)&&trim((string)$data['status'])!=='')$status=mb_substr(trim((string)$data['status']),0,80);
        elseif(array_key_exists('active',$data))$status=((int)$data['active'])===1?'active':'inactive';
        $relations=[];
        foreach(self::RELATIONS[$entityType]??[] as $field){$value=$data[$field]??null;if(is_string($value)&&$this->validId($value))$relations[$field]=$value;}
        return ['id'=>$id,'revision'=>$revision,'label'=>$label,'status'=>$status,'relations'=>$relations];
    }

    /** @return array<string,mixed> */
    private function decodeCursor(string $cursor):array
    {
        if(!preg_match('/^[A-Za-z0-9_-]+$/D',$cursor))throw new InvalidArgumentException('invalid intake context cursor');
        $raw=base64_decode(strtr($cursor,'-_','+/').str_repeat('=',(4-strlen($cursor)%4)%4),true);
        if($raw===false)throw new InvalidArgumentException('invalid intake context cursor');
        try{$value=json_decode($raw,true,8,JSON_THROW_ON_ERROR);}catch(JsonException $error){throw new InvalidArgumentException('invalid intake context cursor',0,$error);}
        if(!is_array($value)||($value['v']??null)!==1||!is_string($value['g']??null)||!preg_match('/^[0-9a-f]{64}$/D',(string)$value['g'])||!is_string($value['t']??null)||!isset(self::OBJECTS[(string)$value['t']])||!is_string($value['a']??null))throw new InvalidArgumentException('invalid intake context cursor');
        return $value;
    }

    private function encodeCursor(string $generation,string $entityType,string $anchor):string
    {
        $raw=json_encode(['v'=>1,'g'=>$generation,'t'=>$entityType,'a'=>$anchor],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
        return rtrim(strtr(base64_encode($raw),'+/','-_'),'=');
    }

    private function validId(string $value):bool{return (bool)preg_match('/^[A-Za-z0-9][A-Za-z0-9._:|\\-]{0,190}$/D',$value);}
}
