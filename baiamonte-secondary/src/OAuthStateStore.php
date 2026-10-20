<?php
declare(strict_types=1);

final class OAuthStateStore
{
    private PDO $db;public function __construct(PDO $db){$this->db=$db;}
    /** @return array{state:string,verifier:string} */
    public function begin(string $now,int $ttl=300):array{$now=DatabaseTime::from($now);$state=$this->random();$verifier=$this->random(48);$expires=DatabaseTime::from($now,max(60,min(600,$ttl)));$q=$this->db->prepare('INSERT INTO oauth_states(state_hash,verifier_value,created_at,expires_at) VALUES(?,?,?,?)');$q->execute([hash('sha256',$state),$verifier,$now,$expires]);return ['state'=>$state,'verifier'=>$verifier];}
    public function consume(string $state,string $now):string{$now=DatabaseTime::from($now);$hash=hash('sha256',$state);$this->db->beginTransaction();try{$q=$this->db->prepare('SELECT verifier_value,expires_at,used_at FROM oauth_states WHERE state_hash=?');$q->execute([$hash]);$r=$q->fetch(PDO::FETCH_ASSOC);if(!$r||$r['used_at']!==null||strtotime((string)$r['expires_at'])<=strtotime($now))throw new RuntimeException('invalid or expired OAuth state');$u=$this->db->prepare('UPDATE oauth_states SET used_at=? WHERE state_hash=? AND used_at IS NULL');$u->execute([$now,$hash]);if($u->rowCount()!==1)throw new RuntimeException('OAuth state replay');$this->db->commit();return (string)$r['verifier_value'];}catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}}
    private function random(int $bytes=32):string{return rtrim(strtr(base64_encode(random_bytes($bytes)),'+/','-_'),'=');}
}
