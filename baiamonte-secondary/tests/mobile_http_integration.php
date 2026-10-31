<?php
declare(strict_types=1);

require __DIR__.'/../src/DatabaseTime.php';
require __DIR__.'/../src/AuthService.php';
require __DIR__.'/../src/MobileAuthContract.php';
require __DIR__.'/../src/MobileHttpBoundary.php';

function httpOk(bool $condition,string $message):void{if(!$condition)throw new RuntimeException($message);echo "ok - ",$message,"\n";}
/** @return array{status:int,headers:list<string>,body:string} */
function request(string $base,string $path,string $method='GET',array $headers=[],string $body=''):array
{
    $context=stream_context_create(['http'=>['method'=>$method,'header'=>implode("\r\n",$headers),'content'=>$body,'ignore_errors'=>true,'follow_location'=>0,'timeout'=>5]]);
    $result=file_get_contents($base.$path,false,$context);$responseHeaders=$http_response_header??[];$status=0;
    if(isset($responseHeaders[0])&&preg_match('/\s(\d{3})\s/',$responseHeaders[0],$match))$status=(int)$match[1];
    return ['status'=>$status,'headers'=>$responseHeaders,'body'=>is_string($result)?$result:''];
}
/** @param array<string,mixed> $config */
function writeConfig(string $path,array $config):void{file_put_contents($path,"<?php\ndeclare(strict_types=1);\nreturn ".var_export($config,true).";\n",LOCK_EX);}
function cookieHeaders(array $headers,string $prefix):array{return array_values(array_filter($headers,fn(string $line):bool=>str_starts_with(strtolower($line),'set-cookie: '.strtolower($prefix))));}

$tmp=sys_get_temp_dir().'/baiamonte-mobile-http-'.bin2hex(random_bytes(6));mkdir($tmp,0700,true);$dbPath=$tmp.'/test.sqlite';$configPath=$tmp.'/config.php';$logPath=$tmp.'/server.log';
$db=new PDO('sqlite:'.$dbPath);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec(file_get_contents(__DIR__.'/../db/schema.sqlite.sql'));$db->exec(file_get_contents(__DIR__.'/../db/migration-006-mobile-read-session.sqlite.sql'));
$now=DatabaseTime::now();$userId='dddddddd-dddd-4ddd-8ddd-dddddddddddd';$db->prepare('INSERT INTO app_users(user_id,ha_user_id,username,display_name,role,enabled,created_at,last_ha_login_at) VALUES(?,?,?,?,?,?,?,?)')->execute([$userId,'ha-user-1','david','David Rahamin','admin',1,$now,$now]);
$auth=new AuthService($db,3600);$browser=$auth->createSession($userId,'ha',$now);$mobileToken=rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');$db->prepare('INSERT INTO mobile_sessions(token_hash,user_id,client_id,scope,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?,?)')->execute([hash('sha256',$mobileToken),$userId,'com.cantinabaiamonte.vineyard','replica.read',DatabaseTime::from($now),DatabaseTime::from($now,3600),DatabaseTime::from($now)]);
$config=['db_dsn'=>'sqlite:'.$dbPath,'db_user'=>'','db_password'=>'','sync_key_id'=>'test','sync_hmac_key'=>'test','sync_enabled'=>false,'camera_sync_enabled'=>false,'camera_sync_key_id'=>'camera','camera_sync_hmac_key'=>'','session_cookie'=>'baiamonte_secondary','base_path'=>'/erp','public_origin'=>'https://cantinabaiamonte.com','ha_base_url'=>'https://ha.example','ha_client_id'=>'https://cantinabaiamonte.com/erp/','ha_redirect_uri'=>'https://cantinabaiamonte.com/erp/auth/callback','ha_local_username'=>'david','ha_initial_display_name'=>'David Rahamin','webauthn_rp_id'=>'cantinabaiamonte.com','offline_revalidation_seconds'=>604800,'csrf_cookie'=>'baiamonte_csrf','oauth_state_cookie'=>'baiamonte_oauth_state','mobile_auth_enabled'=>false,'mobile_client_id'=>'com.cantinabaiamonte.vineyard','mobile_redirect_uri'=>'baiamonte-vineyard://auth/callback','mobile_state_cookie'=>'baiamonte_mobile_state','mobile_handoff_ttl_seconds'=>300,'mobile_session_ttl_seconds'=>3600,'mobile_read_requests_per_minute'=>10,'mobile_estate_id'=>'00000000-0000-4000-8000-000000000001','session_ttl_seconds'=>3600,'max_snapshot_age_seconds'=>7200,'allowed_objects'=>['wine_lots'],'excluded_fields'=>[],'allowed_command_types'=>['record.update'],'camera_allowlist'=>[]];writeConfig($configPath,$config);
$socket=stream_socket_server('tcp://127.0.0.1:0',$errno,$error);if(!$socket)throw new RuntimeException($error);$address=stream_socket_get_name($socket,false);fclose($socket);$port=(int)substr(strrchr($address,':'),1);$base='http://127.0.0.1:'.$port;
$command=[PHP_BINARY,'-S','127.0.0.1:'.$port,__DIR__.'/../public/index.php'];$environment=$_ENV;$environment['BAIAMONTE_CONFIG']=$configPath;$process=proc_open($command,[0=>['pipe','r'],1=>['file',$logPath,'a'],2=>['file',$logPath,'a']],$pipes,__DIR__.'/..',$environment);if(!is_resource($process))throw new RuntimeException('could not start PHP test server');
try{
    $ready=false;for($i=0;$i<50;$i++){usleep(50000);$connection=@fsockopen('127.0.0.1',$port,$e,$m,0.1);if($connection){fclose($connection);$ready=true;break;}}if(!$ready)throw new RuntimeException('PHP test server did not start');
    $browserCookie='Cookie: baiamonte_secondary='.$browser['session_token'];$bearer='Authorization: Bearer '.$mobileToken;$json='Content-Type: application/json';
    $response=request($base,'/erp/mobile/v1/me','GET',[$browserCookie]);httpOk($response['status']===401,'disabled mobile me rejects a valid browser cookie');
    $challenge=rtrim(strtr(base64_encode(hash('sha256',str_repeat('v',43),true)),'+/','-_'),'=');$startPath='/erp/auth/mobile/start?'.http_build_query(['client_id'=>'com.cantinabaiamonte.vineyard','redirect_uri'=>'baiamonte-vineyard://auth/callback','code_challenge'=>$challenge],'','&',PHP_QUERY_RFC3986);$response=request($base,$startPath);httpOk($response['status']===401,'disabled mobile start fails closed without creating a browser session');
    $config['mobile_auth_enabled']=true;writeConfig($configPath,$config);clearstatcache(true,$configPath);
    $response=request($base,'/erp/mobile/v1/me','GET',[$bearer,$browserCookie]);$payload=json_decode($response['body'],true);httpOk($response['status']===200&&($payload['user']['username']??'')==='david'&&($payload['user']['role']??'')==='admin'&&($payload['scope']??'')==='replica.read','valid bearer resolves David and ignores the mixed browser cookie');
    httpOk(in_array('Cache-Control: no-store',$response['headers'],true)&&in_array('Referrer-Policy: no-referrer',$response['headers'],true)&&in_array('Strict-Transport-Security: max-age=31536000; includeSubDomains',$response['headers'],true),'mobile response preserves no-store no-referrer and HSTS headers');
    httpOk(request($base,'/erp/mobile/v1/me','GET',[$browserCookie])['status']===401,'enabled mobile me never falls back to browser cookie');
    httpOk(request($base,'/erp/mobile/v1/me','GET',['Authorization: Bearer invalid',$browserCookie])['status']===401,'invalid bearer never falls back to browser cookie');
    foreach([['/erp/api/admin/sync-config','GET',''],['/erp/api/commands','POST','{}'],['/erp/api/camera-snapshots','POST','{}']] as [$path,$method,$body])httpOk(request($base,$path,$method,[$bearer,$browserCookie,$json,'X-CSRF-Token: '.$browser['csrf_token']],$body)['status']===401,'mixed bearer cannot reach '.$path);
    httpOk(request($base,'/erp/mobile/v1/payroll','GET',[$bearer])['status']===404,'valid mobile bearer cannot discover payroll through an unknown mobile route');
    httpOk(request($base,'/erp/api/status','GET',[$browserCookie])['status']===200,'ordinary browser session remains usable without an Authorization header');
    $startA=request($base,$startPath);$startB=request($base,$startPath);$cookiesA=cookieHeaders($startA['headers'],'baiamonte_mobile_state_');$cookiesB=cookieHeaders($startB['headers'],'baiamonte_mobile_state_');httpOk($startA['status']===302&&$startB['status']===302&&count($cookiesA)===1&&count($cookiesB)===1&&$cookiesA[0]!==$cookiesB[0],'parallel mobile starts use independent HA-state-bound cookies');
    $browserStart=request($base,'/erp/auth/start');httpOk($browserStart['status']===302&&cookieHeaders($browserStart['headers'],'baiamonte_mobile_state_')===[],'ordinary browser HA start is not marked as a mobile transaction');
    $quotaReached=false;for($i=0;$i<20;$i++){if(request($base,'/erp/mobile/v1/me','GET',[$bearer])['status']===401){$quotaReached=true;break;}}httpOk($quotaReached,'real mobile data route reaches its configured per-session quota');httpOk(request($base,'/erp/mobile/v1/session/revoke','POST',[$bearer])['status']===200,'quota-exhausted bearer can revoke immediately through the real router');httpOk(request($base,'/erp/mobile/v1/session/revoke','POST',[$bearer])['status']===200,'real mobile revocation is idempotent');httpOk(request($base,'/erp/mobile/v1/me','GET',[$bearer])['status']===401,'revoked bearer fails subsequent mobile reads');
}finally{proc_terminate($process);proc_close($process);}
$log=is_file($logPath)?file_get_contents($logPath):'';$syntheticAppCode=str_repeat('c',43);$syntheticLocation=MobileHttpBoundary::callbackLocation('baiamonte-vineyard://auth/callback',$syntheticAppCode,str_repeat('d',43));httpOk(str_contains($syntheticLocation,'#code='.$syntheticAppCode)&&!str_contains($syntheticLocation,'?'),'app callback code is confined to the non-request URL fragment');httpOk(!str_contains($log,$mobileToken)&&!str_contains($log,$browser['session_token'])&&!str_contains($log,$browser['csrf_token'])&&!str_contains($log,$syntheticAppCode),'HTTP server log redacts bearer session CSRF and app callback credentials');
foreach([$configPath,$dbPath,$logPath] as $path)if(is_file($path))unlink($path);rmdir($tmp);echo "ALL MOBILE HTTP TESTS PASSED\n";
