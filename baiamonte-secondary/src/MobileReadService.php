<?php
declare(strict_types=1);

final class MobileReadService
{
    private ReplicaService $replica;
    private string $estateId;
    /** @var array<string,true> */
    private array $upstreamObjects;

    /** @var array<string,list<string>> */
    private const ROLE_OBJECTS=[
        'viewer'=>['wine_lots','cellar_containers','vintage_summaries'],
        'operator'=>['wine_lots','cellar_containers','vintage_summaries','harvest_lots','fermentation_observations'],
        'admin'=>['wine_lots','cellar_containers','vintage_summaries','harvest_lots','fermentation_observations'],
    ];
    /** @var array<string,list<string>> */
    private const FIELDS=[
        'wine_lots'=>['code','name','stage','volume_l','variety_summary','current_container_id','started_at','updated_at'],
        'cellar_containers'=>['code','name','container_type','material','capacity_l','location','status','active'],
        'vintage_summaries'=>['vintage_year','variety_name','grapes_kg','wine_l','cassette_count','evidence_status'],
        'harvest_lots'=>['season_id','block_id','variety_id','harvested_at','weight_kg','crate_count','avg_crate_kg','destination','brix','babo','ph','ta_g_l','condition_grade'],
        'fermentation_observations'=>['wine_lot_id','observed_at','vessel_name','stage','temp_c','density_sg','brix','ph','cap_management','quantity','unit','next_check_at','status'],
    ];

    /** @param list<string> $upstreamObjects */
    public function __construct(ReplicaService $replica,array $upstreamObjects,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=$estateId;$this->upstreamObjects=array_fill_keys(array_map('strval',$upstreamObjects),true);
    }

    /** Freshness only: never return upstream error text, snapshot identifiers or whole-replica counts. @return array<string,mixed> */
    public function status(string $now):array
    {
        $status=$this->replica->status($now);
        return [
            'last_success_at'=>$status['last_success_at'],
            'source_generated_at'=>$status['source_generated_at'],
            'data_age_seconds'=>$status['data_age_seconds'],
            'source_app_version'=>$status['source_app_version'],
            'remote_contract_version'=>$status['remote_contract_version'],
            'supported_contract_version'=>$status['supported_contract_version'],
            'state'=>$status['last_success_at']===null?'unavailable':($status['last_error']===null?'ready':'degraded'),
        ];
    }

    /** @return list<string> */
    public function catalog(string $role):array
    {
        return array_values(array_filter(self::ROLE_OBJECTS[$role]??[],fn(string $object):bool=>isset($this->upstreamObjects[$object])));
    }

    /** @return list<array<string,mixed>> */
    public function records(string $role,string $object):array
    {
        if(!in_array($object,$this->catalog($role),true)||!isset(self::FIELDS[$object]))throw new DomainException('mobile object is not permitted');
        $out=[];
        foreach($this->replica->records($object) as $record){
            $data=is_array($record['data']??null)?$record['data']:[];
            if(!isset($data['estate_id'])||!is_string($data['estate_id'])||!hash_equals($this->estateId,$data['estate_id']))continue;
            $safe=[];
            foreach(self::FIELDS[$object] as $field){
                if(!array_key_exists($field,$data))continue;
                $value=$data[$field];
                if(is_array($value)||is_object($value))continue;
                $safe[$field]=$value;
            }
            $out[]=['id'=>(string)$record['id'],'revision'=>(string)$record['revision'],'source_updated_at'=>$record['source_updated_at'],'data'=>$safe];
        }
        return $out;
    }
}
