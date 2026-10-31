<?php
declare(strict_types=1);

if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
$root=dirname(__DIR__);require $root.'/vendor/autoload.php';foreach(['DatabaseTime','MobileFieldIntakeContract','MobileIntakeService'] as $class)require $root.'/src/'.$class.'.php';
$configPath=$argv[1]??getenv('BAIAMONTE_CONFIG');if(!$configPath||!is_file($configPath))throw new RuntimeException('private config path is required');$cfg=require $configPath;
if(($cfg['mobile_field_intake_enabled']??false)!==true){echo "mobile_intake_cleanup disabled\n";exit;}
$db=new PDO($cfg['db_dsn'],$cfg['db_user'],$cfg['db_password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);$service=new MobileIntakeService($db,(string)$cfg['mobile_estate_id'],(string)$cfg['mobile_intake_private_dir']);$deleted=$service->sweep(DatabaseTime::now());$health=$service->health();
echo json_encode(['ok'=>true,'deleted'=>$deleted,'health'=>$health],JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES)."\n";
