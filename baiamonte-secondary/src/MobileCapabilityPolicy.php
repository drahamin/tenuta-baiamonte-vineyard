<?php
declare(strict_types=1);

final class MobileCapabilityPolicy
{
    /** @var array<string,list<string>> */
    private const ROLE_CAPABILITIES=[
        'viewer'=>['replica.read'],
        'operator'=>['replica.read','commands.read','commands.enqueue'],
        'admin'=>[
            'replica.read','commands.read','commands.enqueue','camera.still',
            'admin.sync.read','admin.sync.rotate',
        ],
    ];
    /** @var list<string> */
    private const STEP_UP=['commands.enqueue','camera.still','admin.sync.rotate'];

    /** @param list<string> $tokenCapabilities @return list<string> */
    public static function effective(string $role,array $tokenCapabilities):array
    {
        $roleCapabilities=self::ROLE_CAPABILITIES[$role]??[];
        return array_values(array_intersect($roleCapabilities,array_values(array_unique(array_map('strval',$tokenCapabilities)))));
    }

    /** @param list<string> $tokenCapabilities */
    public static function allows(string $role,array $tokenCapabilities,string $capability):bool
    {
        return in_array($capability,self::effective($role,$tokenCapabilities),true);
    }

    public static function requiresStepUp(string $capability):bool{return in_array($capability,self::STEP_UP,true);}
}
