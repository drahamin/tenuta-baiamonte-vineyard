<?php
declare(strict_types=1);

final class MobileCalendarService
{
    private ReplicaService $replica;
    private string $estateId;

    public function __construct(ReplicaService $replica,string $estateId)
    {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i',$estateId))throw new InvalidArgumentException('valid mobile estate boundary is required');
        $this->replica=$replica;$this->estateId=$estateId;
    }

    /** @return list<array<string,mixed>> */
    public function events(string $role):array
    {
        if(!in_array($role,['operator','admin'],true))throw new DomainException('mobile calendar role is not permitted');
        $events=[];
        foreach([
            'tasks'=>['due_date','work','title'],
            'work_activities'=>['activity_date','planned_work','title'],
            'harvest_plans'=>['planned_pick_date','harvest_projection',null],
            'issues_decisions'=>['due_date','issue_due','issue_text'],
        ] as $object=>[$dateField,$kind,$titleField]){
            foreach($this->replica->records($object) as $record){
                $data=is_array($record['data']??null)?$record['data']:[];
                if(($data['estate_id']??null)!==$this->estateId)continue;
                $start=$this->date($data[$dateField]??null);if($start===null)continue;
                $status=$this->text($data['status']??null,40);
                if(in_array(strtolower($status??''),['cancelled','rejected'],true))continue;
                $title=$titleField===null?'Projected harvest':$this->text($data[$titleField]??null,160);
                if($title===null)$title=match($kind){'planned_work'=>'Planned work','issue_due'=>'Issue due',default=>'Estate work'};
                $end=$object==='work_activities'?$this->date($data['end_date']??null):null;
                $events[]=[
                    'id'=>$object.':'.(string)$record['id'],'kind'=>$kind,'title'=>$title,
                    'start'=>$start,'end'=>$end??$start,'all_day'=>true,'status'=>$status,
                    'priority'=>$this->text($data['priority']??null,20),
                    'source'=>['object'=>$object,'record_id'=>(string)$record['id'],'revision'=>(string)$record['revision']],
                ];
            }
        }
        usort($events,fn(array $a,array $b):int=>[$a['start'],$a['title']]<=>[$b['start'],$b['title']]);
        return array_slice($events,0,500);
    }

    private function date(mixed $value):?string
    {
        if(!is_string($value)||!preg_match('/^\d{4}-\d{2}-\d{2}/D',$value,$match))return null;
        $date=DateTimeImmutable::createFromFormat('!Y-m-d',$match[0]);return $date&&$date->format('Y-m-d')===$match[0]?$match[0]:null;
    }
    private function text(mixed $value,int $limit):?string
    {
        if(!is_string($value))return null;$value=trim($value);return $value===''?null:mb_substr($value,0,$limit);
    }
}
