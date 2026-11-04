<?php
declare(strict_types=1);
require_once __DIR__.'/../src/DatabaseTime.php';
require_once __DIR__.'/../src/ReplicaService.php';
require_once __DIR__.'/../src/MobileEnologyReadService.php';
function enologyCheck(bool $condition,string $message):void{
    if(!$condition)throw new RuntimeException($message);
    echo "ok - ",$message,"\n";
}
$estate='11111111-1111-4111-8111-111111111111';$now='2026-11-04T12:00:00Z';
$db=new PDO('sqlite::memory:');$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
$db->exec(file_get_contents(__DIR__.'/../db/schema.sqlite.sql'));
$records=[['object'=>'wine_lots','id'=>'lot-1','revision'=>1,'source_updated_at'=>$now,
    'data'=>['estate_id'=>$estate,'current_container_id'=>'tank-5']]];
$base=['estate_id'=>$estate,'container_id'=>'tank-5','wine_lot_id'=>'lot-1',
    'observed_at'=>'2026-11-04T09:00:00+01:00','temp_c'=>0,'notes'=>'private-note'];
$cases=[
    'explicit'=>$base,
    'lot-only'=>array_diff_key($base,['container_id'=>true]),
    'wrong-container'=>array_replace($base,['container_id'=>'tank-9']),
    'conflicting-alias'=>array_replace($base,['cellar_container_id'=>'tank-9']),
    'wrong-lot'=>array_replace($base,['wine_lot_id'=>'old-lot']),
    'container-only'=>array_diff_key($base,['wine_lot_id'=>true]),
    'date-only'=>array_replace($base,['observed_at'=>'2026-11-04']),
    'naive'=>array_replace($base,['observed_at'=>'2026-11-04 09:00:00']),
    'relative'=>array_replace($base,['observed_at'=>'tomorrow']),
    'invalid-date'=>array_replace($base,['observed_at'=>'2026-02-30T09:00:00Z']),
    'bad-container-type'=>array_replace($base,['container_id'=>['private']]),
    'other-estate'=>array_replace($base,['estate_id'=>'22222222-2222-4222-8222-222222222222']),
];
foreach($cases as $id=>$data)$records[]=['object'=>'fermentation_observations','id'=>$id,
    'revision'=>9007199254740993,'source_updated_at'=>$now,'data'=>$data];
$snapshot=['snapshot_id'=>'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','source_generated_at'=>$now,'records'=>$records];
$replica=new ReplicaService($db,['wine_lots','cellar_control_profiles','fermentation_observations']);
$replica->importSnapshot($snapshot,json_encode($snapshot,JSON_THROW_ON_ERROR),$now);
$reader=new MobileEnologyReadService($replica,$estate);
$withLot=$reader->history('admin','tank-5','lot-1');
enologyCheck(array_column($withLot,'id')===['explicit'],'exact container and lot only; no current-location inference');
enologyCheck($withLot[0]['observed_at']==='2026-11-04T08:00:00Z','explicit timezone normalized without guessing');
enologyCheck($withLot[0]['revision']==='9007199254740993','lossless revision string');
enologyCheck($withLot[0]['measurements']===[['code'=>'temperature_c','value'=>0.0,'unit'=>'celsius']],'real zero and typed unit');
enologyCheck(!str_contains(json_encode($withLot,JSON_THROW_ON_ERROR),'private'),'private fields do not escape');
$ids=array_column($reader->history('operator','tank-5'),'id');sort($ids);
enologyCheck($ids===['container-only','explicit'],'container-only reading excluded when an exact lot was requested');
$prior=date_default_timezone_get();date_default_timezone_set('Pacific/Honolulu');
try{enologyCheck($reader->history('admin','tank-5','lot-1')===$withLot,'PHP default timezone cannot date unknown observations');}
finally{date_default_timezone_set($prior);}
try{$reader->history('viewer','tank-5');throw new RuntimeException('viewer accepted');}
catch(DomainException $expected){enologyCheck(true,'viewer remains denied');}
try{$reader->history('admin','tank-5','other-lot');throw new RuntimeException('stale lot accepted');}
catch(DomainException $expected){enologyCheck(true,'current-lot precondition preserved');}
