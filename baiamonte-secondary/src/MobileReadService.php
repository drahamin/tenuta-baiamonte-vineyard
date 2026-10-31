<?php
declare(strict_types=1);

final class MobileReadService
{
    private ReplicaService $replica;
    /** @var list<string> */
    private array $allowedObjects;

    /** @param list<string> $allowedObjects */
    public function __construct(ReplicaService $replica,array $allowedObjects)
    {
        $this->replica=$replica;
        $this->allowedObjects=array_values(array_map('strval',$allowedObjects));
    }

    /** @return array<string,mixed> */
    public function status(string $now):array{return $this->replica->status($now);}
    /** @return list<string> */
    public function catalog():array{return $this->allowedObjects;}
    /** @return list<array<string,mixed>> */
    public function records(string $object):array{return $this->replica->records($object);}
}
