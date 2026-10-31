<?php
declare(strict_types=1);

final class MobileWeatherService
{
    private ReplicaService $replica;
    private string $estateId;
    private int $staleAfter;

    public function __construct(ReplicaService $replica,string $estateId,int $staleAfter=3600)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=$estateId;$this->staleAfter=max(300,min(21600,$staleAfter));
    }

    /** @return array<string,mixed> */
    public function banner(string $role,string $now):array
    {
        if(!in_array($role,['viewer','operator','admin'],true))throw new DomainException('mobile weather role is not permitted');
        $latest=null;$latestTime=null;
        foreach($this->replica->records('weather_observations') as $record){
            $data=is_array($record['data']??null)?$record['data']:[];
            if(($data['estate_id']??null)!==$this->estateId)continue;
            $observed=$data['observed_at']??null;$timestamp=is_string($observed)?strtotime($observed):false;
            if($timestamp===false)continue;
            if($latestTime===null||$timestamp>$latestTime){$latest=$data;$latestTime=$timestamp;}
        }
        if(!is_array($latest)||$latestTime===null)return $this->unavailable();
        $clock=strtotime($now);if($clock===false)return $this->unavailable();
        $age=max(0,$clock-$latestTime);
        return [
            'state'=>$age<=$this->staleAfter?'current':'stale',
            'measurement_kind'=>'measured',
            'temperature'=>['value'=>$this->number($latest['temp_c']??null),'unit'=>'celsius'],
            // The replicated station observations do not contain an authoritative
            // condition label. Never infer one from temperature or rainfall.
            'condition'=>null,
            'rain'=>['value'=>$this->number($latest['rain_rate_mm_h']??null),'unit'=>'millimetres_per_hour'],
            'wind'=>[
                'speed'=>$this->number($latest['wind_kph']??null),
                'gust'=>$this->number($latest['wind_gust_kph']??null),
                'unit'=>'kilometres_per_hour',
            ],
            'source'=>'estate_station_replica',
            'observed_at'=>gmdate('Y-m-d\TH:i:s\Z',$latestTime),
            'data_age_seconds'=>$age,
            'stale_after_seconds'=>$this->staleAfter,
        ];
    }

    /** @return array<string,mixed> */
    private function unavailable():array
    {
        return [
            'state'=>'unavailable','measurement_kind'=>null,
            'temperature'=>['value'=>null,'unit'=>'celsius'],'condition'=>null,
            'rain'=>['value'=>null,'unit'=>'millimetres_per_hour'],
            'wind'=>['speed'=>null,'gust'=>null,'unit'=>'kilometres_per_hour'],
            'source'=>null,'observed_at'=>null,'data_age_seconds'=>null,
            'stale_after_seconds'=>$this->staleAfter,
        ];
    }

    private function number(mixed $value):?float
    {
        return is_int($value)||is_float($value)?(float)$value:null;
    }
}
