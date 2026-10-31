<?php
declare(strict_types=1);

final class MobileAuthService
{
    private PDO $db;
    private int $handoffTtl;
    private int $sessionTtl;
    private int $readLimit;

    public function __construct(PDO $db,int $handoffTtl=MobileAuthContract::HANDOFF_TTL_SECONDS,int $sessionTtl=MobileAuthContract::SESSION_TTL_SECONDS,int $readLimit=120)
    {
        $this->db=$db;$this->handoffTtl=$handoffTtl;$this->sessionTtl=$sessionTtl;$this->readLimit=max(10,min(600,$readLimit));
    }

    /** @return array{state:string,expires_at:string} */
    public function begin(string $clientId,string $redirectUri,string $codeChallenge,string $oauthState,string $now):array
    {
        if(!hash_equals(MobileAuthContract::CLIENT_ID,$clientId))throw new InvalidArgumentException('mobile client is not allowed');
        if(!hash_equals(MobileAuthContract::REDIRECT_URI,$redirectUri))throw new InvalidArgumentException('mobile redirect URI is not allowed');
        if(!preg_match('/^[A-Za-z0-9_-]{43}$/D',$codeChallenge))throw new InvalidArgumentException('invalid PKCE S256 challenge');
        if(!preg_match('/^[A-Za-z0-9_-]{43,128}$/D',$oauthState))throw new InvalidArgumentException('invalid HA OAuth state binding');
        $now=DatabaseTime::from($now);$window=DatabaseTime::from($now,-60);
        $rate=$this->db->prepare('SELECT COUNT(*) FROM mobile_auth_transactions WHERE created_at>=? AND consumed_at IS NULL');$rate->execute([$window]);
        if((int)$rate->fetchColumn()>=20)throw new RuntimeException('mobile authentication is temporarily limited');
        $expires=DatabaseTime::from($now,$this->handoffTtl);$state=$this->random();
        $q=$this->db->prepare('INSERT INTO mobile_auth_transactions(state_hash,oauth_state_hash,client_id,redirect_uri,code_challenge,created_at,expires_at) VALUES(?,?,?,?,?,?,?)');
        $q->execute([hash('sha256',$state),hash('sha256',$oauthState),$clientId,$redirectUri,$codeChallenge,$now,$expires]);
        return ['state'=>$state,'expires_at'=>$expires];
    }

    /** Bind a one-time handoff to the enabled pre-provisioned account matching the verified HA identity. @return array{code:string,state:string,redirect_uri:string,expires_at:string} */
    public function authorizeHaIdentity(string $state,string $oauthState,string $haUserId,string $now):array
    {
        $now=DatabaseTime::from($now);$stateHash=hash('sha256',$state);$code=$this->random();$codeHash=hash('sha256',$code);
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT client_id,redirect_uri,expires_at,authorized_at,consumed_at,oauth_state_hash FROM mobile_auth_transactions WHERE state_hash=?');$q->execute([$stateHash]);$tx=$q->fetch(PDO::FETCH_ASSOC);
            if(!$tx||strtotime((string)$tx['expires_at'])<=strtotime($now)||$tx['authorized_at']!==null||$tx['consumed_at']!==null)throw new RuntimeException('mobile authorization transaction is invalid');
            if(!hash_equals((string)$tx['oauth_state_hash'],hash('sha256',$oauthState)))throw new RuntimeException('mobile authorization transaction is not bound to this HA login');
            $u=$this->db->prepare('SELECT user_id,username,display_name,role,enabled FROM app_users WHERE ha_user_id=?');$u->execute([$haUserId]);$user=$u->fetch(PDO::FETCH_ASSOC);
            if(!$user||(int)$user['enabled']!==1)throw new RuntimeException('HA identity is not approved for mobile access');
            $claim=$this->db->prepare('UPDATE mobile_auth_transactions SET user_id=?,authorization_code_hash=?,authorized_at=? WHERE state_hash=? AND authorized_at IS NULL AND consumed_at IS NULL');
            $claim->execute([(string)$user['user_id'],$codeHash,$now,$stateHash]);
            if($claim->rowCount()!==1)throw new RuntimeException('mobile authorization transaction was already claimed');
            $this->audit($now,(string)$user['user_id'],'mobile.authorization.authorized','mobile_auth_transaction',$stateHash,['client_id'=>(string)$tx['client_id']]);
            $this->db->commit();
            return ['code'=>$code,'state'=>$state,'redirect_uri'=>(string)$tx['redirect_uri'],'expires_at'=>(string)$tx['expires_at']];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @return array{access_token:string,token_type:string,scope:string,expires_at:string,user:array{user_id:string,username:string,display_name:string,role:string}} */
    public function exchange(string $state,string $code,string $codeVerifier,string $now):array
    {
        if(!preg_match('/^[A-Za-z0-9._~-]{43,128}$/D',$codeVerifier))throw new InvalidArgumentException('invalid PKCE verifier');
        $now=DatabaseTime::from($now);$stateHash=hash('sha256',$state);$codeHash=hash('sha256',$code);
        $challenge=rtrim(strtr(base64_encode(hash('sha256',$codeVerifier,true)),'+/','-_'),'=');
        $token=$this->random();$tokenHash=hash('sha256',$token);$expires=DatabaseTime::from($now,$this->sessionTtl);
        $attempt=$this->db->prepare('UPDATE mobile_auth_transactions SET exchange_attempts=exchange_attempts+1 WHERE state_hash=? AND consumed_at IS NULL AND exchange_attempts<5');$attempt->execute([$stateHash]);
        if($attempt->rowCount()!==1)throw new RuntimeException('mobile authorization code is invalid');
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT t.user_id,t.client_id,t.code_challenge,t.authorization_code_hash,t.expires_at,t.authorized_at,t.consumed_at,u.username,u.display_name,u.role,u.enabled FROM mobile_auth_transactions t LEFT JOIN app_users u ON u.user_id=t.user_id WHERE t.state_hash=?');$q->execute([$stateHash]);$tx=$q->fetch(PDO::FETCH_ASSOC);
            if(!$tx||$tx['authorized_at']===null||$tx['consumed_at']!==null||strtotime((string)$tx['expires_at'])<=strtotime($now))throw new RuntimeException('mobile authorization code is invalid');
            if(!is_string($tx['authorization_code_hash'])||!hash_equals((string)$tx['authorization_code_hash'],$codeHash)||!hash_equals((string)$tx['code_challenge'],$challenge))throw new RuntimeException('mobile authorization code is invalid');
            if((int)$tx['enabled']!==1)throw new RuntimeException('user is not enabled');
            $claim=$this->db->prepare('UPDATE mobile_auth_transactions SET consumed_at=? WHERE state_hash=? AND consumed_at IS NULL');$claim->execute([$now,$stateHash]);
            if($claim->rowCount()!==1)throw new RuntimeException('mobile authorization code was already consumed');
            $insert=$this->db->prepare('INSERT INTO mobile_sessions(token_hash,user_id,client_id,scope,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?,?)');
            $insert->execute([$tokenHash,(string)$tx['user_id'],(string)$tx['client_id'],MobileAuthContract::SCOPE,$now,$expires,$now]);
            $this->audit($now,(string)$tx['user_id'],'mobile.session.created','mobile_session',$tokenHash,['client_id'=>(string)$tx['client_id'],'scope'=>MobileAuthContract::SCOPE]);
            $this->db->commit();
            return ['access_token'=>$token,'token_type'=>'Bearer','scope'=>MobileAuthContract::SCOPE,'expires_at'=>$expires,'user'=>$this->publicUser($tx)];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @return array{user_id:string,username:string,display_name:string,role:string,scope:string,expires_at:string} */
    public function requireReadSession(string $token,string $now):array
    {
        if($token==='')throw new RuntimeException('authentication required');
        $now=DatabaseTime::from($now);$hash=hash('sha256',$token);
        $q=$this->db->prepare('SELECT u.user_id,u.username,u.display_name,u.role,u.enabled,s.scope,s.expires_at,s.revoked_at FROM mobile_sessions s JOIN app_users u ON u.user_id=s.user_id WHERE s.token_hash=?');$q->execute([$hash]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row||(int)$row['enabled']!==1||$row['revoked_at']!==null||strtotime((string)$row['expires_at'])<=strtotime($now)||!hash_equals(MobileAuthContract::SCOPE,(string)$row['scope']))throw new RuntimeException('authentication required');
        $this->claimReadRate($hash,$now);
        $this->db->prepare('UPDATE mobile_sessions SET last_seen_at=? WHERE token_hash=?')->execute([$now,$hash]);
        return $this->publicUser($row)+['scope'=>(string)$row['scope'],'expires_at'=>(string)$row['expires_at']];
    }

    public function revoke(string $token,string $now):void
    {
        $now=DatabaseTime::from($now);$hash=hash('sha256',$token);
        $q=$this->db->prepare('SELECT user_id FROM mobile_sessions WHERE token_hash=? AND revoked_at IS NULL');$q->execute([$hash]);$userId=$q->fetchColumn();
        $this->db->prepare('UPDATE mobile_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL')->execute([$now,$hash]);
        if(is_string($userId))$this->audit($now,$userId,'mobile.session.revoked','mobile_session',$hash,[]);
    }

    /** @param array<string,mixed> $row @return array{user_id:string,username:string,display_name:string,role:string} */
    private function publicUser(array $row):array{return ['user_id'=>(string)$row['user_id'],'username'=>(string)$row['username'],'display_name'=>(string)$row['display_name'],'role'=>(string)$row['role']];}
    /** @param array<string,mixed> $details */
    private function audit(string $now,string $actor,string $action,string $type,string $id,array $details):void{$this->db->prepare('INSERT INTO audit_events(occurred_at,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)')->execute([$now,$actor,$action,$type,$id,json_encode($details,JSON_THROW_ON_ERROR)]);}
    private function claimReadRate(string $tokenHash,string $now):void
    {
        $threshold=DatabaseTime::from($now,-60);
        $reset=$this->db->prepare('UPDATE mobile_sessions SET rate_window_started_at=?,rate_request_count=1 WHERE token_hash=? AND (rate_window_started_at IS NULL OR rate_window_started_at<=?)');$reset->execute([$now,$tokenHash,$threshold]);
        if($reset->rowCount()===1)return;
        $claim=$this->db->prepare('UPDATE mobile_sessions SET rate_request_count=rate_request_count+1 WHERE token_hash=? AND rate_window_started_at>? AND rate_request_count<?');$claim->execute([$tokenHash,$threshold,$this->readLimit]);
        if($claim->rowCount()!==1)throw new RuntimeException('mobile read rate limit exceeded');
    }
    private function random():string{return rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');}
}
