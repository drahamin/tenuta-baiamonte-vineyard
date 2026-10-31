<?php
declare(strict_types=1);

if(PHP_SAPI!=='cli'||!isset($argv[1])){fwrite(STDERR,"usage: php mobile_estate_binding_check.php /private/config.php\n");exit(2);}
$cfg=require $argv[1];$db=new PDO((string)$cfg['db_dsn'],(string)$cfg['db_user'],(string)$cfg['db_password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
$objects=['wine_lots','cellar_containers','vintage_summaries','harvest_lots','fermentation_observations'];$placeholders=implode(',',array_fill(0,count($objects),'?'));
$sql="SELECT r.object_name,COUNT(*) row_count,COUNT(DISTINCT JSON_UNQUOTE(JSON_EXTRACT(r.data_json,'$.estate_id'))) estate_count,MIN(JSON_UNQUOTE(JSON_EXTRACT(r.data_json,'$.estate_id'))) min_estate_id,MAX(JSON_UNQUOTE(JSON_EXTRACT(r.data_json,'$.estate_id'))) max_estate_id,SUM(JSON_EXTRACT(r.data_json,'$.estate_id') IS NULL) missing_estate FROM replica_records r JOIN sync_state s ON s.active_snapshot_id=r.snapshot_id WHERE s.singleton=1 AND r.object_name IN ($placeholders) GROUP BY r.object_name ORDER BY r.object_name";
$query=$db->prepare($sql);$query->execute($objects);echo json_encode(['objects'=>$query->fetchAll(),'expected_objects'=>$objects],JSON_THROW_ON_ERROR|JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES),"\n";
