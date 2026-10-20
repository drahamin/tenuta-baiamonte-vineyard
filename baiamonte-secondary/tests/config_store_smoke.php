<?php
declare(strict_types=1);

require $argv[1].'/src/ConfigStore.php';
$path=sys_get_temp_dir().'/erp-config-test-'.getmypid().'.php';
$initial=['sync_enabled'=>false,'sync_key_id'=>'old','sync_hmac_key'=>''];
file_put_contents($path,"<?php\nreturn ".var_export($initial,true).";\n");
chmod($path,0600);
$secret=rtrim(strtr(base64_encode(str_repeat('x',32)),'+/','-_'),'=');
$result=ConfigStore::updateSync($path,$initial,['enabled'=>true,'key_id'=>'test-1','secret'=>$secret]);
$saved=require $path;
$passed=$result['enabled']&&$result['secret_configured']&&!array_key_exists('secret',$result)&&$saved['sync_hmac_key']===$secret&&substr(sprintf('%o',fileperms($path)),-3)==='600';
unlink($path);
foreach(glob($path.'.pre-sync-*')?:[] as $backup)unlink($backup);
echo $passed?"config_store_ok secret_redacted=true mode=600\n":"config_store_failed\n";
exit($passed?0:1);
