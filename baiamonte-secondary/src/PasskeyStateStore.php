<?php
declare(strict_types=1);

/**
 * WebAuthn persistence and replay protection. Cryptographic attestation and
 * assertion verification must succeed in the pinned library before calling
 * saveCredential() or recordSuccessfulAssertion().
 */
final class PasskeyStateStore
{
    private PDO $db;
    public function __construct(PDO $db){$this->db=$db;}

    public function storeChallenge(string $challenge,string $purpose,?string $userId,string $now,int $ttl=300):void
    {
        if(!in_array($purpose,['register','authenticate'],true)||$challenge==='')throw new InvalidArgumentException('invalid passkey challenge');
        $expires=gmdate('c',strtotime($now)+max(60,min(600,$ttl)));
        $q=$this->db->prepare('INSERT INTO webauthn_challenges(challenge_hash,user_id,purpose,created_at,expires_at) VALUES(?,?,?,?,?)');$q->execute([hash('sha256',$challenge),$userId,$purpose,$now,$expires]);
    }

    /** @return array{challenge:string,expires_at:string} */
    public function begin(string $purpose,?string $userId,string $now,int $ttl=300):array
    {
        if(!in_array($purpose,['register','authenticate'],true))throw new InvalidArgumentException('invalid passkey purpose');
        if($purpose==='register'&&$userId===null)throw new InvalidArgumentException('registration requires an authenticated user');
        $challenge=rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');
        $expires=gmdate('c',strtotime($now)+max(60,min(600,$ttl)));
        $q=$this->db->prepare('INSERT INTO webauthn_challenges(challenge_hash,user_id,purpose,created_at,expires_at) VALUES(?,?,?,?,?)');
        $q->execute([hash('sha256',$challenge),$userId,$purpose,$now,$expires]);
        return ['challenge'=>$challenge,'expires_at'=>$expires];
    }

    public function consume(string $challenge,string $purpose,string $now):?string
    {
        $hash=hash('sha256',$challenge);$this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT user_id,purpose,expires_at,used_at FROM webauthn_challenges WHERE challenge_hash=?');$q->execute([$hash]);$row=$q->fetch(PDO::FETCH_ASSOC);
            if(!$row||$row['purpose']!==$purpose||$row['used_at']!==null||strtotime((string)$row['expires_at'])<=strtotime($now))throw new RuntimeException('invalid or expired passkey challenge');
            $u=$this->db->prepare('UPDATE webauthn_challenges SET used_at=? WHERE challenge_hash=? AND used_at IS NULL');$u->execute([$now,$hash]);
            if($u->rowCount()!==1)throw new RuntimeException('passkey challenge replay');
            $this->db->commit();return $row['user_id']===null?null:(string)$row['user_id'];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @param list<string> $transports */
    public function saveCredential(string $credentialId,string $userId,string $publicKeyPem,int $signCount,array $transports,string $now):void
    {
        if($credentialId===''||$publicKeyPem===''||$signCount<0)throw new InvalidArgumentException('invalid verified credential');
        $q=$this->db->prepare('INSERT INTO passkey_credentials(credential_id,user_id,public_key_pem,sign_count,transports_json,created_at) VALUES(?,?,?,?,?,?)');
        $q->execute([$credentialId,$userId,$publicKeyPem,$signCount,json_encode(array_values($transports),JSON_THROW_ON_ERROR),$now]);
    }

    public function recordSuccessfulAssertion(string $credentialId,int $newSignCount,string $now):string
    {
        $q=$this->db->prepare('SELECT user_id,sign_count,revoked_at FROM passkey_credentials WHERE credential_id=?');$q->execute([$credentialId]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row||$row['revoked_at']!==null)throw new RuntimeException('unknown or revoked passkey');
        $old=(int)$row['sign_count'];if($old>0&&$newSignCount<=$old)throw new RuntimeException('passkey signature counter did not advance');
        if($newSignCount<0)throw new InvalidArgumentException('invalid signature counter');
        $this->db->prepare('UPDATE passkey_credentials SET sign_count=?,last_used_at=? WHERE credential_id=?')->execute([$newSignCount,$now,$credentialId]);
        return (string)$row['user_id'];
    }

    /** @return list<string> */
    public function credentialIds(string $userId):array{$q=$this->db->prepare('SELECT credential_id FROM passkey_credentials WHERE user_id=? AND revoked_at IS NULL');$q->execute([$userId]);return array_map(fn($r)=>(string)$r['credential_id'],$q->fetchAll(PDO::FETCH_ASSOC));}

    /** @return array{user_id:string,public_key_pem:string,sign_count:int} */
    public function credential(string $credentialId):array{$q=$this->db->prepare('SELECT user_id,public_key_pem,sign_count FROM passkey_credentials WHERE credential_id=? AND revoked_at IS NULL');$q->execute([$credentialId]);$r=$q->fetch(PDO::FETCH_ASSOC);if(!$r)throw new RuntimeException('unknown or revoked passkey');return ['user_id'=>(string)$r['user_id'],'public_key_pem'=>(string)$r['public_key_pem'],'sign_count'=>(int)$r['sign_count']];}
}
