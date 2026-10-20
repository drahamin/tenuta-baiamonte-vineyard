<?php
declare(strict_types=1);

if(PHP_SAPI!=='cli'||!isset($argv[1])){fwrite(STDERR,"usage: php verify_authenticated_release.php CONFIG\n");exit(2);}
$cfg=require $argv[1];
require __DIR__.'/../src/AuthService.php';
$db=new PDO((string)$cfg['db_dsn'],(string)$cfg['db_user'],(string)$cfg['db_password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$userQuery=$db->prepare("SELECT user_id FROM app_users WHERE username=? AND role='admin' AND enabled=1 LIMIT 1");
$userQuery->execute([(string)$cfg['ha_local_username']]);
$user=$userQuery->fetch(PDO::FETCH_ASSOC);
if(!$user)throw new RuntimeException('approved admin user unavailable');
$auth=new AuthService($db,(int)$cfg['session_ttl_seconds']);$now=gmdate('c');$session=$auth->createSession((string)$user['user_id'],'ha',$now);
try{
    $context=stream_context_create(['http'=>['method'=>'GET','header'=>'Cookie: '.(string)$cfg['session_cookie'].'='.$session['session_token']."\r\n",'ignore_errors'=>true,'timeout'=>15]]);
    $html=file_get_contents('https://cantinabaiamonte.com/erp/app',false,$context);
    if(!is_string($html)||!str_contains($html,'Estate operations')||!str_contains($html,'data-view="projects"'))throw new RuntimeException('authenticated app verification failed');
    $js=file_get_contents('https://cantinabaiamonte.com/erp/assets/harvest.js');
    foreach(['installWorkPlanParity','initVintageSelector','camera-snapshots','history.pushState'] as $marker)if(!is_string($js)||!str_contains($js,$marker))throw new RuntimeException('missing release marker '.$marker);
    $status=json_decode((string)file_get_contents('https://cantinabaiamonte.com/erp/api/status',false,$context),true,512,JSON_THROW_ON_ERROR);$sync=$status['sync']??[];
    echo "authenticated_release_ok work_plan=true year_switcher=true camera_code=true source_version=",$sync['source_app_version']??'unknown'," contract=",$sync['remote_contract_version']??'legacy'," records=",$sync['record_count']??0," age_seconds=",$sync['data_age_seconds']??'unknown',"\n";
}finally{$auth->revoke($session['session_token'],gmdate('c'));}
