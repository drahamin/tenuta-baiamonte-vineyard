<?php
declare(strict_types=1);

final class MobileEnologyReadService
{
    private ReplicaService $replica;
    private string $estateId;

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=$estateId;
    }

    /** @return list<array<string,mixed>> */
    public function history(string $role,string $containerId,?string $wineLotId=null):array
    {
        if(!in_array($role,['operator','admin'],true))throw new DomainException('mobile enology role is not permitted');
        if(!$this->id($containerId))throw new InvalidArgumentException('valid container id is required');
        $mappedLots=[];
        foreach($this->replica->records('wine_lots') as $record){
            $data=is_array($record['data']??null)?$record['data']:[];
            if(($data['estate_id']??null)===$this->estateId&&($data['current_container_id']??null)===$containerId)$mappedLots[]=(string)$record['id'];
        }
        if($wineLotId!==null&&$wineLotId!==''){
            if(!$this->id($wineLotId)||!in_array($wineLotId,$mappedLots,true))throw new DomainException('wine lot is not currently assigned to this container');
            $mappedLots=[$wineLotId];
        }
        $out=[];
        foreach(['cellar_control_profiles','fermentation_observations'] as $object){
            foreach($this->replica->records($object) as $record){
                $data=is_array($record['data']??null)?$record['data']:[];
                if(($data['estate_id']??null)!==$this->estateId)continue;
                $recordContainer=(string)($data['container_id']??$data['cellar_container_id']??'');$recordLot=(string)($data['wine_lot_id']??'');
                $containerMatches=$recordContainer!==''&&hash_equals($containerId,$recordContainer);
                $lotMatches=$object==='fermentation_observations'&&$recordLot!==''&&in_array($recordLot,$mappedLots,true);
                if(!$containerMatches&&!$lotMatches)continue;
                $observed=$data['observed_at']??null;if(!is_string($observed)||strtotime($observed)===false)continue;
                $measurements=[];
                foreach(['babo'=>['degree_babo','babo'],'temperature_c'=>['celsius','temp_c'],'density_sg'=>['specific_gravity','density_sg'],'brix'=>['degree_brix','brix'],'ph'=>['pH','ph']] as $code=>[$unit,$field]){
                    $value=$data[$field]??null;if(is_int($value)||is_float($value))$measurements[]=['code'=>$code,'value'=>(float)$value,'unit'=>$unit];
                }
                if(!$measurements)continue;
                $out[]=['id'=>(string)$record['id'],'revision'=>(string)$record['revision'],'source_object'=>$object,'container_id'=>$containerId,'wine_lot_id'=>$recordLot!==''?$recordLot:null,'observed_at'=>gmdate('Y-m-d\TH:i:s\Z',(int)strtotime($observed)),'measurements'=>$measurements,'status'=>is_string($data['status']??null)?$data['status']:'authoritative'];
            }
        }
        usort($out,fn(array $a,array $b):int=>strcmp($b['observed_at'],$a['observed_at']));return array_slice($out,0,250);
    }

    private function id(string $value):bool{return (bool)preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$value);}
}
