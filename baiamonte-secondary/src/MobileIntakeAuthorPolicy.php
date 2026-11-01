<?php
declare(strict_types=1);

/** Exact, default-off author boundary for the first mobile intake pilot. */
final class MobileIntakeAuthorPolicy
{
    private bool $enabled=false;
    private string $websiteUserId='';
    private string $websiteUsername='';
    private string $haUserId='';
    /** @var list<string> */
    private array $kinds=[];

    /** @param array<string,mixed> $configuration */
    public function __construct(array $configuration=[])
    {
        if(($configuration['enabled']??false)!==true)return;
        $websiteUserId=strtolower(trim((string)($configuration['website_user_id']??'')));
        $websiteUsername=mb_strtolower(trim((string)($configuration['website_username']??'')));
        $haUserId=strtolower(trim((string)($configuration['ha_user_id']??'')));
        $kinds=array_values(array_unique(array_map('strval',(array)($configuration['allowed_kinds']??[]))));
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$websiteUserId)
            ||$websiteUsername===''||!preg_match('/^[0-9a-f]{32}$/D',$haUserId)
            ||$kinds!==['enology_reading'])throw new InvalidArgumentException('mobile intake author policy is invalid');
        $this->enabled=true;$this->websiteUserId=$websiteUserId;$this->websiteUsername=$websiteUsername;$this->haUserId=$haUserId;$this->kinds=$kinds;
    }

    /** @param array<string,mixed> $actor */
    public function allows(array $actor,?string $kind=null):bool
    {
        if(!$this->enabled)return false;
        if(!hash_equals($this->websiteUserId,strtolower(trim((string)($actor['user_id']??''))))
            ||!hash_equals($this->websiteUsername,mb_strtolower(trim((string)($actor['username']??''))))
            ||!hash_equals($this->haUserId,strtolower(trim((string)($actor['ha_user_id']??'')))))return false;
        return $kind===null||in_array($kind,$this->kinds,true);
    }

    /** @param array<string,mixed> $actor @return list<string> */
    public function sessionCapabilities(array $actor):array{return $this->allows($actor)?['intake.submit']:[];}
}
