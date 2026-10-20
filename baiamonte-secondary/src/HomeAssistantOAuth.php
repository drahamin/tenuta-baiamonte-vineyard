<?php
declare(strict_types=1);

final class HomeAssistantOAuth
{
    private OAuthStateStore $states;private string $base;private string $clientId;private string $redirect;
    public function __construct(OAuthStateStore $states,string $base,string $clientId,string $redirect){$this->states=$states;$this->base=rtrim($base,'/');$this->clientId=$clientId;$this->redirect=$redirect;if(!str_starts_with($this->base,'https://'))throw new InvalidArgumentException('HA OAuth requires HTTPS');}
    /** @return array{url:string,state:string} */
    public function begin(string $now):array{$s=$this->states->begin($now);$challenge=rtrim(strtr(base64_encode(hash('sha256',$s['verifier'],true)),'+/','-_'),'=');return ['url'=>$this->base.'/auth/authorize?'.http_build_query(['client_id'=>$this->clientId,'redirect_uri'=>$this->redirect,'state'=>$s['state'],'code_challenge'=>$challenge,'code_challenge_method'=>'S256'],'','&',PHP_QUERY_RFC3986),'state'=>$s['state']];}
    /** @return array{access_token:string,refresh_token:string} */
    public function exchange(string $code,string $state,string $now):array{$verifier=$this->states->consume($state,$now);$ch=curl_init($this->base.'/auth/token');curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>15,CURLOPT_HTTPHEADER=>['Content-Type: application/x-www-form-urlencoded'],CURLOPT_POSTFIELDS=>http_build_query(['grant_type'=>'authorization_code','code'=>$code,'client_id'=>$this->clientId,'code_verifier'=>$verifier],'','&',PHP_QUERY_RFC3986)]);$body=curl_exec($ch);$status=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE);$error=curl_error($ch);curl_close($ch);if(!is_string($body)||$status!==200)throw new RuntimeException('HA token exchange failed'.($error!==''?': '.$error:''));$r=json_decode($body,true,512,JSON_THROW_ON_ERROR);if(!is_string($r['access_token']??null)||!is_string($r['refresh_token']??null))throw new RuntimeException('HA token response incomplete');return ['access_token'=>$r['access_token'],'refresh_token'=>$r['refresh_token']];}
    public function revoke(string $refreshToken):void{$ch=curl_init($this->base.'/auth/revoke');curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>10,CURLOPT_HTTPHEADER=>['Content-Type: application/x-www-form-urlencoded'],CURLOPT_POSTFIELDS=>http_build_query(['token'=>$refreshToken],'','&',PHP_QUERY_RFC3986)]);curl_exec($ch);curl_close($ch);}
    public function websocketUrl():string{return 'wss://'.parse_url($this->base,PHP_URL_HOST).'/api/websocket';}
}
