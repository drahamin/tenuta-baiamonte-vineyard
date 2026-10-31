<?php
declare(strict_types=1);

final class MobileTelemetryConflict extends DomainException {}
final class MobileTelemetryForbidden extends DomainException {}
final class MobileTelemetryRequestError extends InvalidArgumentException {}

final class MobileTelemetryService
{
    public const CONTRACT='baiamonte.mobile-telemetry.v1';
    private const ENERGY_OBJECT='ro_estate_energy_observations';
    private const ETNA_OBJECT='ro_etna_status';
    private const ENERGY_ROLES=['operator','admin'];
    private const ETNA_ROLES=['viewer','operator','admin'];
    private const ENERGY_FIELDS=['pv_power_w','estate_load_w','battery_soc_pct','battery_power_w','forecast_remaining_kwh'];
    private const ENERGY_UNITS=[
        'pv_power_w'=>'W','estate_load_w'=>'W','battery_soc_pct'=>'%',
        'battery_power_w'=>'W','forecast_remaining_kwh'=>'kWh',
    ];

    private ReplicaService $replica;
    private string $estateId;

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iD',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=strtolower($estateId);
    }

    /** @param array<string,mixed> $query @return array<string,mixed> */
    public function energy(string $role,array $query,string $now):array
    {
        if(!in_array($role,self::ENERGY_ROLES,true))throw new MobileTelemetryForbidden('mobile role is not permitted');
        foreach(array_keys($query) as $key)if((string)$key!=='range')throw new MobileTelemetryRequestError('unsupported mobile energy filter');
        if(isset($query['range'])&&!is_string($query['range']))throw new MobileTelemetryRequestError('invalid mobile energy range');
        $range=is_string($query['range']??null)?(string)$query['range']:'24h';
        if(!in_array($range,['24h','7d'],true))throw new MobileTelemetryRequestError('unsupported mobile energy range');
        $nowAt=$this->time($now);if($nowAt===null)throw new MobileTelemetryRequestError('invalid current time');
        $before=$this->replica->status($now);$snapshot=(string)($before['active_snapshot_id']??'');
        $available=$snapshot!==''&&$this->replica->permitsObject(self::ENERGY_OBJECT);$points=[];
        if($available){
            $cutoff=$nowAt-($range==='24h'?86400:604800);
            foreach($this->replica->records(self::ENERGY_OBJECT) as $record){
                $data=is_array($record['data']??null)?$record['data']:[];
                if(!is_string($data['estate_id']??null)||!hash_equals($this->estateId,strtolower((string)$data['estate_id'])))continue;
                $observedAt=$this->time($data['observed_at']??null);if($observedAt===null||$observedAt<$cutoff||$observedAt>$nowAt+300)continue;
                $point=['observed_at'=>gmdate('Y-m-d\TH:i:s\Z',$observedAt)];$present=0;
                foreach(self::ENERGY_FIELDS as $field){$value=$this->number($data[$field]??null);$point[$field]=$value;if($value!==null)$present++;}
                $point['quality']=$present===0?'unavailable':($present===count(self::ENERGY_FIELDS)?'observed':'partial');$point['_at']=$observedAt;$points[]=$point;
            }
            usort($points,fn(array $left,array $right):int=>$left['_at']<=>$right['_at']);
            $points=$this->sample($points,$range==='24h'?289:337);
        }
        $after=$this->replica->status($now);if((string)($after['active_snapshot_id']??'')!==$snapshot)throw new MobileTelemetryConflict('mobile replica snapshot changed');
        $latest=$points?$points[count($points)-1]:null;$observedAt=is_array($latest)?(int)$latest['_at']:null;$age=$observedAt===null?null:max(0,$nowAt-$observedAt);
        $freshness=$observedAt===null?'unavailable':($age<=900?'current':'stale');$metrics=[];
        foreach(self::ENERGY_FIELDS as $field){$value=is_array($latest)?$latest[$field]:null;$metrics[$field]=['value'=>$value,'unit'=>self::ENERGY_UNITS[$field],'observed_at'=>$observedAt===null?null:gmdate('Y-m-d\TH:i:s\Z',$observedAt),'quality'=>$value===null?'unavailable':$freshness];}
        foreach($points as &$point)unset($point['_at']);unset($point);
        return [
            'contract'=>self::CONTRACT,'estate_id'=>$this->estateId,'range'=>$range,'available'=>$available&&$latest!==null,
            'source'=>$this->source($after,$snapshot,$freshness),'data_age_seconds'=>$age,
            'metrics'=>$metrics,'series'=>['units'=>self::ENERGY_UNITS,'points'=>$points],
            'battery_power_sign'=>'positive_discharge_negative_charge',
        ];
    }

    /** @param array<string,mixed> $query @return array<string,mixed> */
    public function etna(string $role,array $query,string $now):array
    {
        if(!in_array($role,self::ETNA_ROLES,true))throw new MobileTelemetryForbidden('mobile role is not permitted');
        if($query!==[])throw new MobileTelemetryRequestError('Etna route accepts no filters');
        $nowAt=$this->time($now);if($nowAt===null)throw new MobileTelemetryRequestError('invalid current time');
        $before=$this->replica->status($now);$snapshot=(string)($before['active_snapshot_id']??'');$record=null;
        if($snapshot!==''&&$this->replica->permitsObject(self::ETNA_OBJECT))foreach($this->replica->records(self::ETNA_OBJECT) as $candidate)if((string)($candidate['id']??'')==='current'){$record=$candidate;break;}
        $data=is_array($record['data']??null)?$record['data']:[];$expiresAt=$this->time($data['expires_at']??null);$generatedAt=$this->time($data['generated_at']??null);
        $fresh=$record!==null&&($data['fresh']??false)===true&&$expiresAt!==null&&$expiresAt>$nowAt&&(array)($data['stale_sources']??[])===[];$allReportedSourcesCurrent=true;
        $sources=[];foreach((array)($data['source_status']??[]) as $name=>$source){
            if(!in_array((string)$name,['communications','vona','ash_advisory','vaac','civil_protection','regional_civil_protection','seismic','bulletin','webcams'],true)||!is_array($source))continue;
            $sourceExpires=$this->time($source['expires_at']??null);$sourceCurrent=(string)($source['state']??'')==='current'&&$sourceExpires!==null&&$sourceExpires>$nowAt;
            if(!$sourceCurrent)$allReportedSourcesCurrent=false;$sourceQuality=$sourceCurrent?'current':($source===[]?'unavailable':'stale');
            $sources[]=['name'=>(string)$name,'state'=>$sourceQuality,'last_success_at'=>$this->iso($source['last_success_at']??null),'expires_at'=>$this->iso($source['expires_at']??null),'quality'=>$sourceQuality];
        }
        $fresh=$fresh&&$allReportedSourcesCurrent;$quality=$record===null?'unavailable':($fresh?'current':'stale');
        $summary=['activity_label'=>null,'activity_code'=>null,'aviation_colour_code'=>null,'civil_protection_level'=>null,'ash_status'=>null,'ash_current'=>null];$events=[];
        if($fresh){
            $activity=is_array($data['activity']??null)?$data['activity']:[];$civil=is_array($data['civil_protection']??null)?$data['civil_protection']:[];$ash=is_array($data['ash_advisory']??null)?$data['ash_advisory']:[];
            $summary=['activity_label'=>$this->text($activity['label']??null,160),'activity_code'=>$this->text($activity['code']??null,80),'aviation_colour_code'=>$this->text($activity['aviation_colour_code']??null,16),'civil_protection_level'=>$this->text($civil['published_level']??($civil['level']??null),32),'ash_status'=>$this->text($ash['status']??null,32),'ash_current'=>($ash['current']??false)===true];
            foreach(array_slice((array)($data['seismic_events']??[]),0,20) as $event)if(is_array($event))$events[]=['time'=>$this->iso($event['time']??null),'magnitude'=>$this->number($event['magnitude']??null),'depth_km'=>$this->number($event['depth_km']??null),'place'=>$this->text($event['place']??null,160),'quality'=>'current_source_cache'];
        }
        $after=$this->replica->status($now);if((string)($after['active_snapshot_id']??'')!==$snapshot)throw new MobileTelemetryConflict('mobile replica snapshot changed');
        return [
            'contract'=>self::CONTRACT,'available'=>$record!==null,'fresh'=>$fresh,'quality'=>$quality,
            'generated_at'=>$generatedAt===null?null:gmdate('Y-m-d\TH:i:s\Z',$generatedAt),'expires_at'=>$expiresAt===null?null:gmdate('Y-m-d\TH:i:s\Z',$expiresAt),
            'source'=>$this->source($after,$snapshot,$quality),'summary'=>$summary,'source_status'=>$sources,'recent_seismic_events'=>$events,
            'stale_message'=>$fresh?null:'Cached source data is expired; no current status or all-clear can be inferred.',
            'safety_note'=>$this->text($data['safety_note']??null,300)??'No current status can be inferred. Check INGV, Civil Protection and local authorities.',
        ];
    }

    /** @param array<string,mixed> $status @return array<string,mixed> */
    private function source(array $status,string $snapshot,string $state):array{return ['source_generated_at'=>$this->iso($status['source_generated_at']??null),'last_success_at'=>$this->iso($status['last_success_at']??null),'data_age_seconds'=>$status['data_age_seconds']??null,'state'=>$snapshot===''?'unavailable':$state];}
    private function time(mixed $value):?int{if(!is_string($value)||trim($value)==='')return null;$time=strtotime($value);return $time===false?null:$time;}
    private function iso(mixed $value):?string{$time=$this->time($value);return $time===null?null:gmdate('Y-m-d\TH:i:s\Z',$time);}
    private function number(mixed $value):?float{if(is_int($value)||is_float($value))return is_finite((float)$value)?(float)$value:null;if(is_string($value)&&is_numeric($value))return is_finite((float)$value)?(float)$value:null;return null;}
    private function text(mixed $value,int $limit):?string{if(!is_string($value))return null;$value=trim($value);return $value===''?null:mb_substr($value,0,$limit);}
    /** @param list<array<string,mixed>> $points @return list<array<string,mixed>> */
    private function sample(array $points,int $limit):array{if(count($points)<=$limit)return $points;$sampled=[];$last=count($points)-1;for($index=0;$index<$limit;$index++)$sampled[]=$points[(int)floor($index*$last/($limit-1))];return $sampled;}
}
