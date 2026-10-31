<?php
declare(strict_types=1);

foreach(['DatabaseTime','MobileFieldIntakeContract','MobileIntakeService'] as $class)require __DIR__.'/../src/'.$class.'.php';

const ESTATE='00000000-0000-4000-8000-000000000001';
const USER_ID='dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const TOKEN_HASH='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

function payload(string $uuid):array
{
    $attachments=[];
    for($index=0;$index<5;$index++)$attachments[]=['sha256'=>hash('sha256',$uuid.'-'.$index),'media_type'=>'image/png','byte_count'=>15728640,'filename'=>'quota-'.$index.'.png'];
    return ['report_uuid'=>$uuid,'kind'=>'enology_reading','estate_id'=>ESTATE,'occurred_at'=>'2026-10-20T09:00:00+02:00','client_created_at'=>'2026-10-20T09:01:00+02:00','source_timezone'=>'Europe/Rome','entities'=>['container_id'=>'tank-5','wine_lot_id'=>'lot-1'],'expected_revisions'=>['container_id'=>'8','wine_lot_id'=>'4'],'measurements'=>[['code'=>'babo','value'=>18.1,'unit'=>'degree_babo']],'attachments'=>$attachments];
}

if(($argv[1]??'')==='child'){
    [$script,$mode,$databasePath,$privateDir,$barrier,$uuid]=$argv;
    $db=new PDO('sqlite:'.$databasePath);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE,PDO::FETCH_ASSOC);$db->exec('PRAGMA busy_timeout=5000');
    $deadline=microtime(true)+5;while(!is_file($barrier)&&microtime(true)<$deadline)usleep(1000);
    if(!is_file($barrier)){fwrite(STDERR,"barrier timeout\n");exit(2);}
    $service=new MobileIntakeService($db,ESTATE,$privateDir);
    try{$service->submit(payload($uuid),['user_id'=>USER_ID,'username'=>'approved-admin','role'=>'admin','token_hash'=>TOKEN_HASH,'capabilities'=>['intake.submit']],'2026-10-20T08:00:00+00:00');echo "accepted\n";}
    catch(Throwable $error){echo "rejected\n";}
    exit(0);
}

$directory=sys_get_temp_dir().'/baiamonte-intake-quota-'.bin2hex(random_bytes(6));
if(!mkdir($directory,0700,true))throw new RuntimeException('could not create quota test directory');
$databasePath=$directory.'/quota.sqlite';$privateDir=$directory.'/evidence';$barrier=$directory.'/go';$db=new PDO('sqlite:'.$databasePath);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE,PDO::FETCH_ASSOC);
$db->exec((string)file_get_contents(__DIR__.'/../db/schema.sqlite.sql'));$db->exec((string)file_get_contents(__DIR__.'/../db/migration-006-mobile-read-session.sqlite.sql'));$db->exec((string)file_get_contents(__DIR__.'/../db/migration-007-mobile-intake.sqlite.sql'));
$db->prepare('INSERT INTO app_users(user_id,ha_user_id,username,display_name,role,enabled,created_at,last_ha_login_at) VALUES(?,?,?,?,?,?,?,?)')->execute([USER_ID,'ha-user-1','approved-admin','Approved Admin','admin',1,'2026-10-20 08:00:00.000000','2026-10-20 08:00:00.000000']);
$db->prepare('INSERT INTO mobile_sessions(token_hash,user_id,client_id,scope,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?,?)')->execute([TOKEN_HASH,USER_ID,'com.cantinabaiamonte.vineyard','replica.read','2026-10-20 08:00:00.000000','2026-10-20 09:00:00.000000','2026-10-20 08:00:00.000000']);
$db->prepare('INSERT INTO mobile_session_capabilities(token_hash,capability,granted_at) VALUES(?,?,?)')->execute([TOKEN_HASH,'intake.submit','2026-10-20 08:00:00.000000']);
$uuids=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'];$processes=[];
try{
    foreach($uuids as $uuid){$pipes=[];$process=proc_open([PHP_BINARY,__FILE__,'child',$databasePath,$privateDir,$barrier,$uuid],[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);if(!is_resource($process))throw new RuntimeException('could not start quota claimant');fclose($pipes[0]);$processes[]=[$process,$pipes];}
    file_put_contents($barrier,'go',LOCK_EX);$results=[];
    foreach($processes as [$process,$pipes]){$results[]=trim((string)stream_get_contents($pipes[1]));$error=(string)stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$exit=proc_close($process);if($exit!==0)throw new RuntimeException('quota claimant failed: '.$error);}
    sort($results);if($results!==['accepted','rejected'])throw new RuntimeException('exactly one concurrent 75 MiB reservation must succeed');
    $row=$db->query('SELECT COUNT(*) reports,COALESCE(SUM(reserved_attachment_bytes),0) bytes FROM mobile_intake_reports')->fetch(PDO::FETCH_ASSOC);if((int)$row['reports']!==1||(int)$row['bytes']!==78643200)throw new RuntimeException('concurrent reservations exceeded the 100 MiB author limit');
    echo "ALL MOBILE INTAKE QUOTA CONCURRENCY TESTS PASSED\n";
}finally{
    foreach($processes as [$process,$pipes])if(is_resource($process))proc_terminate($process);
    if(is_file($barrier))unlink($barrier);if(is_file($databasePath))unlink($databasePath);@rmdir($privateDir);@rmdir($directory);
}
