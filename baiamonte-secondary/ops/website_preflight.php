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
$mobileKeys=['mobile_client_id','mobile_redirect_uri','mobile_state_cookie','mobile_handoff_ttl_seconds','mobile_session_ttl_seconds','mobile_read_requests_per_minute','mobile_estate_id'];
if($mobileEnabled)$mobileMissing=array_values(array_filter($mobileKeys,fn(string $key):bool=>!isset($cfg[$key])||$cfg[$key]===''));
$mobileColumns=[];$mobileIndexes=[];$mobileEngines=[];$mobileForeignKeys=[];
if($mobileEnabled){
    $mobileSchema=$db->prepare("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=? AND table_name IN ('mobile_auth_transactions','mobile_sessions') ORDER BY table_name,column_name");$mobileSchema->execute([$database]);$mobileColumns=$mobileSchema->fetchAll();
    $indexQuery=$db->prepare("SELECT table_name,index_name,non_unique,GROUP_CONCAT(column_name ORDER BY seq_in_index) columns_csv FROM information_schema.statistics WHERE table_schema=? AND table_name IN ('mobile_auth_transactions','mobile_sessions') GROUP BY table_name,index_name,non_unique ORDER BY table_name,index_name");$indexQuery->execute([$database]);$mobileIndexes=$indexQuery->fetchAll();
    $engineQuery=$db->prepare("SELECT table_name,engine FROM information_schema.tables WHERE table_schema=? AND table_name IN ('mobile_auth_transactions','mobile_sessions') ORDER BY table_name");$engineQuery->execute([$database]);$mobileEngines=$engineQuery->fetchAll();
    $foreignKeyQuery=$db->prepare("SELECT table_name,constraint_name FROM information_schema.referential_constraints WHERE constraint_schema=? AND table_name IN ('mobile_auth_transactions','mobile_sessions') ORDER BY table_name,constraint_name");$foreignKeyQuery->execute([$database]);$mobileForeignKeys=$foreignKeyQuery->fetchAll();
}
$mobileTables=array_values(array_unique(array_map(fn(array $row):string=>(string)$row['table_name'],$mobileColumns)));
$requiredColumns=['mobile_auth_transactions'=>['authorization_code_hash','authorized_at','client_id','code_challenge','consumed_at','created_at','exchange_attempts','expires_at','oauth_state_hash','redirect_uri','state_hash','user_id'],'mobile_sessions'=>['client_id','created_at','expires_at','last_seen_at','rate_request_count','rate_window_started_at','revoked_at','scope','token_hash','user_id']];$actualColumns=[];foreach($mobileColumns as $row)$actualColumns[(string)$row['table_name']][]=(string)$row['column_name'];foreach($actualColumns as &$names)sort($names);unset($names);$missingColumns=[];foreach($requiredColumns as $table=>$names)$missingColumns[$table]=array_values(array_diff($names,$actualColumns[$table]??[]));
$indexSignatures=array_map(fn(array $row):string=>$row['table_name'].':'.$row['index_name'].':'.$row['non_unique'].':'.$row['columns_csv'],$mobileIndexes);$requiredIndexes=['mobile_auth_transactions:PRIMARY:0:state_hash','mobile_auth_transactions:oauth_state_hash:0:oauth_state_hash','mobile_auth_transactions:mobile_auth_transactions_expiry_idx:1:expires_at','mobile_sessions:PRIMARY:0:token_hash','mobile_sessions:mobile_sessions_user_idx:1:user_id,expires_at'];$missingIndexes=array_values(array_diff($requiredIndexes,$indexSignatures));
$engineSignatures=array_map(fn(array $row):string=>$row['table_name'].':'.strtoupper((string)$row['engine']),$mobileEngines);$missingEngines=array_values(array_diff(['mobile_auth_transactions:INNODB','mobile_sessions:INNODB'],$engineSignatures));
$foreignKeySignatures=array_map(fn(array $row):string=>$row['table_name'].':'.$row['constraint_name'],$mobileForeignKeys);$missingForeignKeys=array_values(array_diff(['mobile_auth_transactions:mobile_auth_transactions_user_fk','mobile_sessions:mobile_sessions_user_fk'],$foreignKeySignatures));
$mobileContractValid=!$mobileEnabled||((string)($cfg['mobile_client_id']??'')==='com.cantinabaiamonte.vineyard'&&(string)($cfg['mobile_redirect_uri']??'')==='baiamonte-vineyard://auth/callback'&&preg_match('/^[A-Za-z0-9_-]{1,48}$/D',(string)($cfg['mobile_state_cookie']??''))===1&&(int)($cfg['mobile_handoff_ttl_seconds']??0)===300&&(int)($cfg['mobile_session_ttl_seconds']??0)===3600&&(int)($cfg['mobile_read_requests_per_minute']??0)>=10&&(int)($cfg['mobile_read_requests_per_minute']??0)<=600&&preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',(string)($cfg['mobile_estate_id']??''))===1);
$mobileSchemaReady=!$mobileEnabled||($mobileMissing===[]&&$mobileContractValid&&$mobileTables===['mobile_auth_transactions','mobile_sessions']&&array_filter($missingColumns)===[]&&$missingIndexes===[]&&$missingEngines===[]&&$missingForeignKeys===[]);
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
    'mobile'=>['enabled'=>$mobileEnabled,'missing_config_keys'=>$mobileMissing,'contract_valid'=>$mobileContractValid,'tables'=>$mobileTables,'missing_columns'=>$missingColumns,'missing_indexes'=>$missingIndexes,'missing_engines'=>$missingEngines,'missing_foreign_keys'=>$missingForeignKeys,'schema_ready'=>$mobileSchemaReady],
],JSON_THROW_ON_ERROR|JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES),"\n";
