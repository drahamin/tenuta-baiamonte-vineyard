<?php
declare(strict_types=1);

final class MobileDirectoryService
{
    private ReplicaService $replica;
    private string $estateId;

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=$estateId;
    }

    /** The source view is purpose-built: no HA entity, username, location, payroll or private contact fields. @return list<array<string,mixed>> */
    public function entries(string $role):array
    {
        if(!in_array($role,['viewer','operator','admin'],true))throw new DomainException('mobile directory role is not permitted');
        $out=[];
        foreach($this->replica->records('ro_mobile_directory') as $record){
            $data=is_array($record['data']??null)?$record['data']:[];
            if(($data['estate_id']??null)!==$this->estateId||($data['active']??0)!==1)continue;
            $name=$this->text($data['display_name']??null,120);if($name===null)continue;
            $out[]=[
                'id'=>(string)$record['id'],'revision'=>(string)$record['revision'],
                'display_name'=>$name,'work_role'=>$this->text($data['work_role']??null,100),
                'team'=>$this->text($data['team']??null,80),
            ];
        }
        usort($out,fn(array $a,array $b):int=>strnatcasecmp($a['display_name'],$b['display_name']));return $out;
    }

    private function text(mixed $value,int $limit):?string
    {
        if(!is_string($value))return null;$value=trim($value);return $value===''?null:mb_substr($value,0,$limit);
    }
}
