<?php
declare(strict_types=1);

require __DIR__.'/../src/DatabaseTime.php';
require __DIR__.'/../src/MobileIntakeSyncAuth.php';

if(($argv[1]??'')==='child'){
    [$script,$mode,$databasePath,$barrier,$timestamp,$nonce,$signature]=$argv;
    $db=new PDO('sqlite:'.$databasePath);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec('PRAGMA busy_timeout=5000');
    $deadline=microtime(true)+5;while(!is_file($barrier)&&microtime(true)<$deadline)usleep(1000);
    if(!is_file($barrier)){fwrite(STDERR,"barrier timeout\n");exit(2);}
    try{
        MobileIntakeSyncAuth::verifyAndClaim($db,'POST','/erp/sync/mobile-intake/requests','{"limit":1}','baiamonte-intake-1',$timestamp,$nonce,$signature,str_repeat('s',43),(int)$timestamp);
        echo "accepted\n";
    }catch(RuntimeException $error){echo "rejected\n";}
    exit(0);
}

$directory=sys_get_temp_dir().'/baiamonte-intake-replay-'.bin2hex(random_bytes(6));
if(!mkdir($directory,0700,true))throw new RuntimeException('could not create replay test directory');
$databasePath=$directory.'/nonce.sqlite';$barrier=$directory.'/go';$db=new PDO('sqlite:'.$databasePath);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
$db->exec('CREATE TABLE mobile_intake_request_nonces(nonce_hash TEXT PRIMARY KEY,key_id TEXT NOT NULL,request_method TEXT NOT NULL,request_path TEXT NOT NULL,issued_at TEXT NOT NULL,expires_at TEXT NOT NULL,claimed_at TEXT NOT NULL)');
$timestamp=(string)time();$nonce=rtrim(strtr(base64_encode(str_repeat('r',32)),'+/','-_'),'=');$body='{"limit":1}';$canonical="POST\n/erp/sync/mobile-intake/requests\nbaiamonte-intake-1\n".$timestamp."\n".$nonce."\n".hash('sha256',$body);$signature='sha256='.hash_hmac('sha256',$canonical,str_repeat('s',43));
$command=[PHP_BINARY,__FILE__,'child',$databasePath,$barrier,$timestamp,$nonce,$signature];$processes=[];
try{
    for($i=0;$i<2;$i++){
        $pipes=[];$process=proc_open($command,[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);
        if(!is_resource($process))throw new RuntimeException('could not start replay claimant');
        fclose($pipes[0]);$processes[]=[$process,$pipes];
    }
    file_put_contents($barrier,'go',LOCK_EX);$results=[];
    foreach($processes as [$process,$pipes]){$results[]=trim((string)stream_get_contents($pipes[1]));$error=(string)stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$exit=proc_close($process);if($exit!==0)throw new RuntimeException('claimant failed: '.$error);}
    sort($results);if($results!==['accepted','rejected'])throw new RuntimeException('exactly one concurrent claimant must succeed');
    if((int)$db->query('SELECT COUNT(*) FROM mobile_intake_request_nonces')->fetchColumn()!==1)throw new RuntimeException('persistent replay claim count must be one');
    echo "ALL MOBILE INTAKE REPLAY CONCURRENCY TESTS PASSED\n";
}finally{
    foreach($processes as [$process,$pipes]){if(is_resource($process))proc_terminate($process);}
    if(is_file($barrier))unlink($barrier);if(is_file($databasePath))unlink($databasePath);@rmdir($directory);
}
