<?php
declare(strict_types=1);

final class ReplicaService
{
    public const SUPPORTED_CONTRACT_VERSION = 2;
    private PDO $db;
    /** @var array<string, true> */
    private array $allowed;
    /** @var array<string, array<string, true>> */
    private array $excludedFields;

    /** @param list<string> $allowedObjects @param array<string,list<string>> $excludedFields */
    public function __construct(PDO $db, array $allowedObjects, array $excludedFields=[])
    {
        $this->db = $db;
        $this->allowed = array_fill_keys($allowedObjects, true);
        $this->excludedFields = [];
        foreach ($excludedFields as $object => $fields) {
            $this->excludedFields[(string)$object] = array_fill_keys(array_map('strval', $fields), true);
        }
    }

    /** @param array<string,mixed> $snapshot */
    public function importSnapshot(array $snapshot, string $rawBody, string $now): void
    {
        $id = self::uuid((string)($snapshot['snapshot_id'] ?? ''));
        $generated = self::timestamp((string)($snapshot['source_generated_at'] ?? ''));
        $records = $snapshot['records'] ?? null;
        $sourceVersion=(string)($snapshot['source_app_version']??'unknown');$contract=$snapshot['remote_contract_version']??null;
        if($sourceVersion!=='unknown'&&!preg_match('/^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/D',$sourceVersion))throw new InvalidArgumentException('invalid source app version');
        if($contract!==null&&(!is_int($contract)||$contract<1||$contract>self::SUPPORTED_CONTRACT_VERSION))throw new DomainException('remote contract version is not supported');
        if (!is_array($records)) {
            throw new InvalidArgumentException('records must be an array');
        }

        $seen = [];
        foreach ($records as $record) {
            if (!is_array($record)) {
                throw new InvalidArgumentException('record must be an object');
            }
            $object = (string)($record['object'] ?? '');
            if (!isset($this->allowed[$object])) {
                throw new InvalidArgumentException('object is not permitted: '.$object);
            }
            $recordId = trim((string)($record['id'] ?? ''));
            if ($recordId === '' || strlen($recordId) > 191) {
                throw new InvalidArgumentException('invalid record id');
            }
            $revision = filter_var($record['revision'] ?? null, FILTER_VALIDATE_INT);
            if ($revision === false || $revision < 0) {
                throw new InvalidArgumentException('invalid revision');
            }
            if (!array_key_exists('data', $record) || !is_array($record['data'])) {
                throw new InvalidArgumentException('record data must be an object');
            }
            foreach (array_keys($record['data']) as $field) {
                if (isset($this->excludedFields[$object][(string)$field])) {
                    throw new InvalidArgumentException('field is not permitted: '.$object.'.'.$field);
                }
            }
            $key = $object."\0".$recordId;
            if (isset($seen[$key])) {
                throw new InvalidArgumentException('duplicate object/id in snapshot');
            }
            $seen[$key] = true;
            if (isset($record['source_updated_at']) && $record['source_updated_at'] !== null) {
                self::timestamp((string)$record['source_updated_at']);
            }
        }

        $this->db->beginTransaction();
        try {
            $insertSnapshot = $this->db->prepare(
                'INSERT INTO snapshots(snapshot_id,source_generated_at,received_at,record_count,body_sha256,status) VALUES(?,?,?,?,?,?)'
            );
            $insertSnapshot->execute([$id, $generated, $now, count($records), hash('sha256', $rawBody), 'loading']);
            $insertRecord = $this->db->prepare(
                'INSERT INTO replica_records(snapshot_id,object_name,record_id,revision,source_updated_at,data_json) VALUES(?,?,?,?,?,?)'
            );
            foreach ($records as $record) {
                $insertRecord->execute([
                    $id,
                    (string)$record['object'],
                    (string)$record['id'],
                    (int)$record['revision'],
                    $record['source_updated_at'] ?? null,
                    self::json($record['data']),
                ]);
            }
            $this->db->exec("UPDATE snapshots SET status='retired' WHERE status='active'");
            $activate = $this->db->prepare("UPDATE snapshots SET status='active' WHERE snapshot_id=?");
            $activate->execute([$id]);
            $state = $this->db->prepare(
                'UPDATE sync_state SET active_snapshot_id=?,last_success_at=?,source_generated_at=?,last_error=NULL WHERE singleton=1'
            );
            $state->execute([$id, $now, $generated]);
            $this->audit('ha-sync', 'snapshot.activated', 'snapshot', $id, ['record_count' => count($records),'source_app_version'=>$sourceVersion,'remote_contract_version'=>$contract], $now);
            $this->db->commit();
            $this->retireBoundedHistory();
        } catch (Throwable $e) {
            if ($this->db->inTransaction()) {
                $this->db->rollBack();
            }
            throw $e;
        }
    }

    private function retireBoundedHistory():void
    {
        // Retain two last-good retired snapshots and remove at most two older
        // derived copies per sync. This bounds write amplification and avoids
        // a large purge transaction on the shared host.
        try{
            $ids=$this->db->query("SELECT snapshot_id FROM snapshots WHERE status='retired' ORDER BY received_at DESC LIMIT 2,2")->fetchAll(PDO::FETCH_COLUMN);
            if(!$ids)return;
            $delete=$this->db->prepare('DELETE FROM snapshots WHERE snapshot_id=? AND status=\'retired\'');
            foreach($ids as $snapshotId)$delete->execute([(string)$snapshotId]);
        }catch(Throwable $ignored){
            // Retention is maintenance only; the newly activated snapshot is
            // valid and must not be reported as failed if cleanup is deferred.
        }
    }

    /** @return array<string,mixed> */
    public function status(string $now): array
    {
        $row = $this->db->query('SELECT active_snapshot_id,last_success_at,source_generated_at,last_error FROM sync_state WHERE singleton=1')->fetch(PDO::FETCH_ASSOC);
        $counts = $this->db->query('SELECT COUNT(*) AS record_count,COUNT(DISTINCT r.object_name) AS object_count FROM replica_records r JOIN sync_state s ON s.active_snapshot_id=r.snapshot_id WHERE s.singleton=1')->fetch(PDO::FETCH_ASSOC);
        $age = null;
        if ($row && $row['source_generated_at'] !== null) {
            $age = max(0, strtotime($now) - strtotime((string)$row['source_generated_at']));
        }
        $release=$this->db->query("SELECT details_json FROM audit_events WHERE action='snapshot.activated' ORDER BY event_id DESC LIMIT 1")->fetchColumn();$release=is_string($release)?json_decode($release,true):[];
        return [
            'active_snapshot_id' => $row['active_snapshot_id'] ?? null,
            'last_success_at' => $row['last_success_at'] ?? null,
            'source_generated_at' => $row['source_generated_at'] ?? null,
            'data_age_seconds' => $age,
            'last_error' => $row['last_error'] ?? null,
            'record_count' => (int)($counts['record_count'] ?? 0),
            'object_count' => count($this->allowed),
            'populated_object_count' => (int)($counts['object_count'] ?? 0),
            'source_app_version' => $release['source_app_version'] ?? 'unknown',
            'remote_contract_version' => $release['remote_contract_version'] ?? null,
            'supported_contract_version' => self::SUPPORTED_CONTRACT_VERSION,
        ];
    }

    /** @return list<array<string,mixed>> */
    public function records(string $object): array
    {
        if (!isset($this->allowed[$object])) {
            throw new InvalidArgumentException('object is not permitted');
        }
        $q = $this->db->prepare(
            'SELECT r.record_id,r.revision,r.source_updated_at,r.data_json FROM replica_records r JOIN sync_state s ON s.active_snapshot_id=r.snapshot_id WHERE s.singleton=1 AND r.object_name=? ORDER BY r.record_id'
        );
        $q->execute([$object]);
        $out = [];
        foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $out[] = [
                'id' => $row['record_id'],
                'revision' => (string)$row['revision'],
                'source_updated_at' => $row['source_updated_at'],
                'data' => json_decode((string)$row['data_json'], true, 512, JSON_THROW_ON_ERROR),
            ];
        }
        return $out;
    }

    /** @param array<string,mixed> $details */
    private function audit(string $actor, string $action, string $type, string $id, array $details, string $now): void
    {
        $q = $this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)');
        $q->execute([$now, $actor, $action, $type, $id, self::json($details)]);
    }

    private static function uuid(string $value): string
    {
        if (!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i', $value)) {
            throw new InvalidArgumentException('invalid UUID');
        }
        return strtolower($value);
    }

    private static function timestamp(string $value): string
    {
        $time = strtotime($value);
        if ($value === '' || $time === false) {
            throw new InvalidArgumentException('invalid timestamp');
        }
        return $value;
    }

    /** @param mixed $value */
    private static function json($value): string
    {
        return json_encode($value, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }
}
