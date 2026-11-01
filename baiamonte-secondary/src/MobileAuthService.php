<?php
declare(strict_types=1);

final class MobileAuthService
{
    private PDO $db;
    private int $handoffTtl;
    private int $sessionTtl;
    private int $readLimit;
    /** @var list<string> */
    private array $grantedCapabilities;

    /** @param list<string> $grantedCapabilities */
    public function __construct(PDO $db,int $handoffTtl=MobileAuthContract::HANDOFF_TTL_SECONDS,int $sessionTtl=MobileAuthContract::SESSION_TTL_SECONDS,int $readLimit=120,array $grantedCapabilities=[])
    {
        foreach($grantedCapabilities as $capability)if(!in_array($capability,['intake.submit','light.control'],true))throw new InvalidArgumentException('unknown mobile capability');
        $this->db=$db;$this->handoffTtl=$handoffTtl;$this->sessionTtl=$sessionTtl;$this->readLimit=max(10,min(600,$readLimit));$this->grantedCapabilities=array_values(array_unique(array_map('strval',$grantedCapabilities)));
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
            if(!$tx||strtotime((string)$tx['expires_at'])<=strtotime($now)||$tx['authorized_at']!==null||$tx['consumed_at']!==null)throw new AuthenticationRequired('mobile authorization transaction is invalid');
            if(!hash_equals((string)$tx['oauth_state_hash'],hash('sha256',$oauthState)))throw new AuthenticationRequired('mobile authorization transaction is not bound to this HA login');
            $u=$this->db->prepare('SELECT user_id,username,display_name,role,enabled FROM app_users WHERE ha_user_id=?');$u->execute([$haUserId]);$user=$u->fetch(PDO::FETCH_ASSOC);
            if(!$user||(int)$user['enabled']!==1)throw new AuthorizationDenied('HA identity is not approved for mobile access');
            $claim=$this->db->prepare('UPDATE mobile_auth_transactions SET user_id=?,authorization_code_hash=?,authorized_at=? WHERE state_hash=? AND authorized_at IS NULL AND consumed_at IS NULL');
            $claim->execute([(string)$user['user_id'],$codeHash,$now,$stateHash]);
            if($claim->rowCount()!==1)throw new AuthenticationRequired('mobile authorization transaction was already claimed');
            $this->db->prepare('UPDATE app_users SET last_ha_login_at=? WHERE user_id=? AND enabled=1')->execute([$now,(string)$user['user_id']]);
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
        if($attempt->rowCount()!==1)throw new AuthenticationRequired('mobile authorization code is invalid');
        $this->db->beginTransaction();
        try{
            $q=$this->db->prepare('SELECT t.user_id,t.client_id,t.code_challenge,t.authorization_code_hash,t.expires_at,t.authorized_at,t.consumed_at,u.username,u.display_name,u.role,u.enabled FROM mobile_auth_transactions t LEFT JOIN app_users u ON u.user_id=t.user_id WHERE t.state_hash=?');$q->execute([$stateHash]);$tx=$q->fetch(PDO::FETCH_ASSOC);
            if(!$tx||$tx['authorized_at']===null||$tx['consumed_at']!==null||strtotime((string)$tx['expires_at'])<=strtotime($now))throw new AuthenticationRequired('mobile authorization code is invalid');
            if(!is_string($tx['authorization_code_hash'])||!hash_equals((string)$tx['authorization_code_hash'],$codeHash)||!hash_equals((string)$tx['code_challenge'],$challenge))throw new AuthenticationRequired('mobile authorization code is invalid');
            if((int)$tx['enabled']!==1)throw new AuthorizationDenied('user is not enabled');
            $claim=$this->db->prepare('UPDATE mobile_auth_transactions SET consumed_at=? WHERE state_hash=? AND consumed_at IS NULL');$claim->execute([$now,$stateHash]);
            if($claim->rowCount()!==1)throw new AuthenticationRequired('mobile authorization code was already consumed');
            $insert=$this->db->prepare('INSERT INTO mobile_sessions(token_hash,user_id,client_id,scope,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?,?)');
            $insert->execute([$tokenHash,(string)$tx['user_id'],(string)$tx['client_id'],MobileAuthContract::SCOPE,$now,$expires,$now]);
            $capabilities=MobileCapabilityPolicy::effective((string)$tx['role'],$this->grantedCapabilities);
            $grant=$this->db->prepare('INSERT INTO mobile_session_capabilities(token_hash,capability,granted_at) VALUES(?,?,?)');
            foreach($capabilities as $capability)$grant->execute([$tokenHash,$capability,$now]);
            $this->audit($now,(string)$tx['user_id'],'mobile.session.created','mobile_session',$tokenHash,['client_id'=>(string)$tx['client_id'],'scope'=>MobileAuthContract::SCOPE,'capabilities'=>$capabilities]);
            $this->db->commit();
            return ['access_token'=>$token,'token_type'=>'Bearer','scope'=>MobileAuthContract::SCOPE,'capabilities'=>$capabilities,'expires_at'=>$expires,'user'=>$this->publicUser($tx)];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }

    /** @return array{user_id:string,username:string,display_name:string,role:string,scope:string,expires_at:string} */
    public function requireReadSession(string $token,string $now):array
    {
        return $this->requireSession($token,$now,true);
    }

    public function requireRecentHaStepUp(string $token,string $userId,string $approvedUsername,string $now,int $maxAge=300):void
    {
        $now=DatabaseTime::from($now);$cutoff=DatabaseTime::from($now,-$maxAge);$hash=hash('sha256',$token);
        $q=$this->db->prepare('SELECT s.created_at,s.expires_at,s.revoked_at,u.last_ha_login_at,u.enabled,u.role,u.username,c.capability FROM mobile_sessions s JOIN app_users u ON u.user_id=s.user_id LEFT JOIN mobile_session_capabilities c ON c.token_hash=s.token_hash AND c.capability=\'light.control\' WHERE s.token_hash=? AND s.user_id=?');$q->execute([$hash,$userId]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row||(int)$row['enabled']!==1||$row['role']!=='admin'||!hash_equals($approvedUsername,(string)$row['username'])||$row['revoked_at']!==null||strtotime((string)$row['expires_at'])<=strtotime($now)||$row['capability']!=='light.control'||(string)$row['created_at']<$cutoff||!is_string($row['last_ha_login_at'])||(string)$row['last_ha_login_at']<$cutoff)throw new AuthenticationStepUpRequired('recent HA authentication required');
    }

    /** Revocation remains available after quota exhaustion, expiry, disable or a prior idempotent revoke. */
    public function requireRevokeToken(string $token):void
    {
        if($token==='')throw new AuthenticationRequired('authentication required');$q=$this->db->prepare('SELECT 1 FROM mobile_sessions WHERE token_hash=?');$q->execute([hash('sha256',$token)]);if((int)$q->fetchColumn()!==1)throw new AuthenticationRequired('authentication required');
    }

    /** @return array{user_id:string,username:string,display_name:string,role:string,scope:string,expires_at:string} */
    private function requireSession(string $token,string $now,bool $applyReadRate):array
    {
        if($token==='')throw new AuthenticationRequired('authentication required');
        $now=DatabaseTime::from($now);$hash=hash('sha256',$token);
        $q=$this->db->prepare('SELECT u.user_id,u.username,u.display_name,u.role,u.enabled,s.scope,s.expires_at,s.revoked_at FROM mobile_sessions s JOIN app_users u ON u.user_id=s.user_id WHERE s.token_hash=?');$q->execute([$hash]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row||(int)$row['enabled']!==1||$row['revoked_at']!==null||strtotime((string)$row['expires_at'])<=strtotime($now)||!hash_equals(MobileAuthContract::SCOPE,(string)$row['scope']))throw new AuthenticationRequired('authentication required');
        if($applyReadRate)$this->claimReadRate($hash,$now);
        $this->db->prepare('UPDATE mobile_sessions SET last_seen_at=? WHERE token_hash=?')->execute([$now,$hash]);
        $capabilityQuery=$this->db->prepare('SELECT capability FROM mobile_session_capabilities WHERE token_hash=? ORDER BY capability');$capabilityQuery->execute([$hash]);$capabilities=array_values(array_map('strval',$capabilityQuery->fetchAll(PDO::FETCH_COLUMN)));
        return $this->publicUser($row)+['scope'=>(string)$row['scope'],'capabilities'=>$capabilities,'expires_at'=>(string)$row['expires_at'],'token_hash'=>$hash];
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
        if($claim->rowCount()!==1)throw new MobileReadRateLimit();
    }
    private function random():string{return rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');}
}
