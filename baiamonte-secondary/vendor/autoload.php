<?php
declare(strict_types=1);
spl_autoload_register(static function(string $class):void{
    $prefix='lbuchs\\WebAuthn\\';if(strncmp($class,$prefix,strlen($prefix))!==0)return;
    $path=__DIR__.'/lbuchs/webauthn/src/'.str_replace('\\','/',substr($class,strlen($prefix))).'.php';if(is_file($path))require $path;
});
