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
                $primary=$data['container_id']??null;$alias=$data['cellar_container_id']??null;
                if(($primary!==null&&!is_string($primary))||($alias!==null&&!is_string($alias)))continue;
                if(is_string($primary)&&$primary!==''&&is_string($alias)&&$alias!==''&&!hash_equals($primary,$alias))continue;
                $recordContainer=is_string($primary)&&$primary!==''?$primary:($alias??'');
                $recordLot=$data['wine_lot_id']??'';if(!is_string($recordLot))continue;
                // Current lot location does not prove a historical tank link.
                if($recordContainer===''||!hash_equals($containerId,$recordContainer))continue;
                if($wineLotId!==null&&$wineLotId!==''&&!hash_equals($wineLotId,$recordLot))continue;
                if($recordLot!==''&&!in_array($recordLot,$mappedLots,true))continue;
                $observed=$this->observationTime($data['observed_at']??null);if($observed===null)continue;
                $measurements=[];
                foreach(['babo'=>['degree_babo','babo'],'temperature_c'=>['celsius','temp_c'],'density_sg'=>['specific_gravity','density_sg'],'brix'=>['degree_brix','brix'],'ph'=>['pH','ph']] as $code=>[$unit,$field]){
                    $value=$data[$field]??null;if((is_int($value)||is_float($value))&&is_finite((float)$value))$measurements[]=['code'=>$code,'value'=>(float)$value,'unit'=>$unit];
                }
                if(!$measurements)continue;
                $out[]=['id'=>(string)$record['id'],'revision'=>(string)$record['revision'],'source_object'=>$object,'container_id'=>$recordContainer,'wine_lot_id'=>$recordLot!==''?$recordLot:null,'observed_at'=>$observed,'measurements'=>$measurements,'status'=>is_string($data['status']??null)?$data['status']:'authoritative'];
            }
        }
        usort($out,fn(array $a,array $b):int=>strcmp($b['observed_at'],$a['observed_at']));return array_slice($out,0,250);
    }

    private function id(string $value):bool{return (bool)preg_match('/^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$/D',$value);}

    private function observationTime(mixed $value):?string
    {
        // Neither PHP's timezone nor snapshot/fetch time dates a measurement.
        if(!is_string($value)||!preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1[0-3]):[0-5]\d|[+-]14:00)$/D',$value))return null;
        $format=str_contains($value,'.')?'!Y-m-d\TH:i:s.uP':'!Y-m-d\TH:i:sP';
        $parsed=DateTimeImmutable::createFromFormat($format,$value);
        $errors=DateTimeImmutable::getLastErrors();
        if($parsed===false||(is_array($errors)&&($errors['warning_count']>0||$errors['error_count']>0)))return null;
        return $parsed->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\TH:i:s\Z');
    }
}
