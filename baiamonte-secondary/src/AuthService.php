<?php
declare(strict_types=1);

final class AuthService
{
    private PDO $db;
    private int $ttl;
    private string $lightControlUsername;

    public function __construct(PDO $db, int $ttl=43200,string $lightControlUsername=''){$this->db=$db;$this->ttl=$ttl;$this->lightControlUsername=$lightControlUsername;}

    /** @return array{session_token:string,csrf_token:string,expires_at:string} */
    public function createSession(string $userId,string $method,string $now):array
    {
        if(!in_array($method,['ha','passkey','recovery'],true))throw new InvalidArgumentException('invalid auth method');
        $u=$this->db->prepare('SELECT enabled FROM app_users WHERE user_id=?');$u->execute([$userId]);
        if((int)$u->fetchColumn()!==1)throw new RuntimeException('user is not enabled');
        $now=DatabaseTime::from($now);$token=$this->random();$csrf=$this->random();$expires=DatabaseTime::from($now,$this->ttl);
        $q=$this->db->prepare('INSERT INTO web_sessions(session_hash,user_id,csrf_hash,created_at,expires_at,last_seen_at,auth_method) VALUES(?,?,?,?,?,?,?)');
        $q->execute([hash('sha256',$token),$userId,hash('sha256',$csrf),$now,$expires,$now,$method]);
        return ['session_token'=>$token,'csrf_token'=>$csrf,'expires_at'=>$expires];
    }

    /** @return array{user_id:string,username:string,display_name:string,role:string} */
    public function requireSession(string $token,string $now):array
    {
        $now=DatabaseTime::from($now);
        $q=$this->db->prepare('SELECT u.user_id,u.username,u.display_name,u.role,u.enabled,s.expires_at,s.revoked_at FROM web_sessions s JOIN app_users u ON u.user_id=s.user_id WHERE s.session_hash=?');
        $q->execute([hash('sha256',$token)]);$row=$q->fetch(PDO::FETCH_ASSOC);
        if(!$row || (int)$row['enabled']!==1 || $row['revoked_at']!==null || strtotime((string)$row['expires_at'])<=strtotime($now))throw new RuntimeException('authentication required');
        $this->db->prepare('UPDATE web_sessions SET last_seen_at=? WHERE session_hash=?')->execute([$now,hash('sha256',$token)]);
        return ['user_id'=>$row['user_id'],'username'=>$row['username'],'display_name'=>$row['display_name'],'role'=>$row['role']];
    }

    public function requireCsrf(string $token,string $csrf):void
    {
        $q=$this->db->prepare('SELECT csrf_hash FROM web_sessions WHERE session_hash=?');$q->execute([hash('sha256',$token)]);$expected=$q->fetchColumn();
        if(!is_string($expected)||!hash_equals($expected,hash('sha256',$csrf)))throw new RuntimeException('invalid CSRF token');
    }

    public function requireRecentHaStepUp(string $token,string $userId,string $now,int $maxAge=300):void
    {
        $now=DatabaseTime::from($now);$q=$this->db->prepare('SELECT s.created_at,s.expires_at,s.revoked_at,s.auth_method,u.last_ha_login_at,u.enabled,u.role,u.username FROM web_sessions s JOIN app_users u ON u.user_id=s.user_id WHERE s.session_hash=? AND s.user_id=?');$q->execute([hash('sha256',$token),$userId]);$row=$q->fetch(PDO::FETCH_ASSOC);
        $sessionAge=$row?strtotime($now)-strtotime((string)$row['created_at']):-1;$loginAge=$row&&$row['last_ha_login_at']!==null?strtotime($now)-strtotime((string)$row['last_ha_login_at']):-1;
        $fresh=$row&&$this->lightControlUsername!==''&&$row['auth_method']==='ha'&&$row['revoked_at']===null&&(int)$row['enabled']===1&&$row['role']==='admin'&&hash_equals($this->lightControlUsername,(string)$row['username'])&&strtotime((string)$row['expires_at'])>strtotime($now)&&$sessionAge>=0&&$sessionAge<=$maxAge&&$loginAge>=0&&$loginAge<=$maxAge;
        if(!$fresh)throw new RuntimeException('fresh HA authentication required');
    }

    public function revoke(string $token,string $now):void{$now=DatabaseTime::from($now);$this->db->prepare('UPDATE web_sessions SET revoked_at=? WHERE session_hash=?')->execute([$now,hash('sha256',$token)]);}

    /** Bind only an already-provisioned local account; HA login never creates an ERP user. */
    public function recordHaLogin(string $username,string $haUserId,string $displayName,string $now):string
    {
        $now=DatabaseTime::from($now);
        $this->db->beginTransaction();
        try{$q=$this->db->prepare('SELECT user_id,ha_user_id FROM app_users WHERE username=? AND enabled=1');$q->execute([$username]);$u=$q->fetch(PDO::FETCH_ASSOC);
            if(!$u||($u['ha_user_id']!==null&&!hash_equals((string)$u['ha_user_id'],$haUserId)))throw new RuntimeException('HA user is not approved for ERP access');
            $this->db->prepare('UPDATE app_users SET ha_user_id=?,display_name=?,last_ha_login_at=? WHERE user_id=?')->execute([$haUserId,$displayName,$now,$u['user_id']]);$this->db->commit();return (string)$u['user_id'];
        }catch(Throwable $e){if($this->db->inTransaction())$this->db->rollBack();throw $e;}
    }
    /** @return array{user_id:string,username:string,display_name:string,role:string,ha_user_id:?string} */
    public function provisionedUser(string $username):array{$q=$this->db->prepare('SELECT user_id,username,display_name,role,ha_user_id FROM app_users WHERE username=? AND enabled=1');$q->execute([$username]);$r=$q->fetch(PDO::FETCH_ASSOC);if(!$r)throw new RuntimeException('HA user is not approved for ERP access');return $r;}
    /** @return array{user_id:string,username:string,display_name:string,role:string} */
    public function userById(string $userId):array{$q=$this->db->prepare('SELECT user_id,username,display_name,role FROM app_users WHERE user_id=? AND enabled=1');$q->execute([$userId]);$r=$q->fetch(PDO::FETCH_ASSOC);if(!$r)throw new RuntimeException('user is not enabled');return $r;}

    /** Consume a one-time offline recovery code. No HA password is stored or checked. */
    public function consumeRecoveryCode(string $username,string $code,string $now):string
    {
        $this->db->beginTransaction();
        try {
            $q=$this->db->prepare('SELECT r.code_id,r.code_hash,u.user_id FROM recovery_codes r JOIN app_users u ON u.user_id=r.user_id WHERE u.username=? AND u.enabled=1 AND r.used_at IS NULL');$q->execute([$username]);
            foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row){
                if(!password_verify($code,(string)$row['code_hash']))continue;
                $claim=$this->db->prepare('UPDATE recovery_codes SET used_at=? WHERE code_id=? AND used_at IS NULL');
                $claim->execute([DatabaseTime::from($now),$row['code_id']]);
                if($claim->rowCount()!==1)continue;
                $this->db->commit();
                return (string)$row['user_id'];
            }
            $this->db->rollBack();
            throw new RuntimeException('invalid recovery credential');
        } catch(Throwable $e) {
            if($this->db->inTransaction())$this->db->rollBack();
            throw $e;
        }
    }

    private function random():string{return rtrim(strtr(base64_encode(random_bytes(32)),'+/','-_'),'=');}
}
