<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli' || !isset($argv[1])) {
    fwrite(STDERR, "usage: php website_preflight.php /private/config.php\n");
    exit(2);
}
$cfg=require $argv[1];
$required=['db_dsn','db_user','db_password','session_cookie','allowed_objects','allowed_command_types'];
$missing=array_values(array_filter($required,fn(string $key):bool=>!array_key_exists($key,$cfg)));
$db=new PDO((string)$cfg['db_dsn'],(string)$cfg['db_user'],(string)$cfg['db_password'],[
    PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
]);
$database=(string)$db->query('SELECT DATABASE()')->fetchColumn();
$column=$db->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name='oauth_states' AND column_name IN ('verifier_hash','verifier_value') ORDER BY column_name");
$column->execute([$database]);
$authType=$db->prepare("SELECT column_type FROM information_schema.columns WHERE table_schema=? AND table_name='web_sessions' AND column_name='auth_method'");
$authType->execute([$database]);
$userQuery=$db->prepare('SELECT username,ha_user_id,last_ha_login_at,enabled FROM app_users WHERE username=?');
$userQuery->execute([(string)$cfg['ha_local_username']]);
$user=$userQuery->fetch();
$mobileEnabled=($cfg['mobile_auth_enabled']??false)===true;$mobileMissing=[];
$mobileKeys=['mobile_client_id','mobile_redirect_uri','mobile_state_cookie','mobile_handoff_ttl_seconds','mobile_session_ttl_seconds','mobile_estate_id'];
if($mobileEnabled)$mobileMissing=array_values(array_filter($mobileKeys,fn(string $key):bool=>!isset($cfg[$key])||$cfg[$key]===''));
$mobileColumns=[];
if($mobileEnabled){$mobileSchema=$db->prepare("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=? AND table_name IN ('mobile_auth_transactions','mobile_sessions') ORDER BY table_name,column_name");$mobileSchema->execute([$database]);$mobileColumns=$mobileSchema->fetchAll();}
$mobileTables=array_values(array_unique(array_map(fn(array $row):string=>(string)$row['table_name'],$mobileColumns)));
$mobileContractValid=!$mobileEnabled||((string)($cfg['mobile_client_id']??'')==='com.cantinabaiamonte.vineyard'&&(string)($cfg['mobile_redirect_uri']??'')==='baiamonte-vineyard://auth/callback'&&preg_match('/^[0-9a-f-]{36}$/i',(string)($cfg['mobile_estate_id']??''))===1);
echo json_encode([
    'php'=>PHP_VERSION,
    'extensions'=>['curl'=>extension_loaded('curl'),'openssl'=>extension_loaded('openssl'),'pdo_mysql'=>extension_loaded('pdo_mysql'),'sodium'=>extension_loaded('sodium')],
    'missing_config_keys'=>$missing,
    'database'=>$database,
    'allowed_object_count'=>count((array)$cfg['allowed_objects']),
    'sync_enabled'=>(bool)($cfg['sync_enabled']??false),
    'oauth_state_columns'=>$column->fetchAll(PDO::FETCH_COLUMN),
    'auth_method_type'=>$authType->fetchColumn(),
    'approved_user'=>['exists'=>(bool)$user,'ha_bound'=>$user&&$user['ha_user_id']!==null,'last_ha_login_at'=>$user['last_ha_login_at']??null,'enabled'=>(int)($user['enabled']??0)],
    'mobile'=>['enabled'=>$mobileEnabled,'missing_config_keys'=>$mobileMissing,'contract_valid'=>$mobileContractValid,'tables'=>$mobileTables,'schema_ready'=>!$mobileEnabled||($mobileMissing===[]&&$mobileContractValid&&$mobileTables===['mobile_auth_transactions','mobile_sessions'])],
],JSON_THROW_ON_ERROR|JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES),"\n";
