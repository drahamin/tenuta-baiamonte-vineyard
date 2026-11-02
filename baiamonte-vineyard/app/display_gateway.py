"""Disabled-by-default Cloudflare origin gateway for remote displays."""

from __future__ import annotations

import hmac
import re
import urllib.error
import urllib.request

from fastapi import FastAPI, Header, HTTPException, Request, Response

from .config import get_settings

display_gateway_app=FastAPI(title="Baiamonte Remote Display Gateway",docs_url=None,redoc_url=None,openapi_url=None)
_ASSET=re.compile(r"^tv/assets/[A-Za-z0-9_./-]{1,240}$")
_TRAFFIC=re.compile(r"^tv/(?:api/traffic/(?:adsb|ais)|traffic-app/(?:adsb|ais)/[A-Za-z0-9_./@!$&'()*+,;=~-]{0,300})$")
_LABEL=re.compile(r"^labels/(?:tank|kiosk|api/(?:tank|kiosk))/[A-Za-z0-9-]{16,128}$|^labels/(?:assets|brand|manifest)/[A-Za-z0-9_./:-]{1,240}$|^labels/(?:service-worker\.js|robots\.txt)$")
_TV={"tv","tv/","tv/display","tv/tv","tv/health","tv/api/display-profile","tv/api/display-data"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


_OPENER=urllib.request.build_opener(_NoRedirect)


def classify_display_path(path:str)->tuple[int,str]:
    if any(segment in {".",".."} for segment in path.split("/")):raise HTTPException(404,"not found")
    if path in _TV:return 8101,"/" if path in {"tv","tv/"} else "/"+path.removeprefix("tv/")
    if _ASSET.fullmatch(path) or _TRAFFIC.fullmatch(path):return 8101,"/"+path.removeprefix("tv/")
    if _LABEL.fullmatch(path):return 8102,"/"+path.removeprefix("labels/")
    raise HTTPException(404,"not found")


def _authorize(value:str|None)->None:
    settings=get_settings()
    if not settings.display_gateway_enabled or not settings.display_gateway_origin_token:
        raise HTTPException(503,"display gateway disabled")
    if value is None or not hmac.compare_digest(value,settings.display_gateway_origin_token):
        raise HTTPException(401,"authentication required")


@display_gateway_app.api_route("/{path:path}",methods=["GET","HEAD"])
def relay_display(path:str,request:Request,x_baiamonte_display_gateway:str|None=Header(default=None))->Response:
    settings=get_settings()
    if request.url.hostname.casefold()!=settings.display_gateway_public_host.casefold():raise HTTPException(404,"not found")
    _authorize(x_baiamonte_display_gateway);port,upstream_path=classify_display_path(path)
    if len(request.url.query)>2048:raise HTTPException(422,"query too large")
    if request.url.query:upstream_path+="?"+request.url.query
    upstream=urllib.request.Request(f"http://127.0.0.1:{port}{upstream_path}",method=request.method,headers={"Accept":request.headers.get("accept","*/*"),"User-Agent":request.headers.get("user-agent","Baiamonte-Display-Gateway/1")})
    try:
        with _OPENER.open(upstream,timeout=15) as result:
            body=result.read(4*1024*1024+1);status=result.status;content_type=result.headers.get("Content-Type","application/octet-stream")
    except urllib.error.HTTPError as error:
        body=error.read(64*1024);status=error.code;content_type=error.headers.get("Content-Type","text/plain")
    except (urllib.error.URLError,TimeoutError) as error:
        raise HTTPException(502,"display service unavailable") from error
    if len(body)>4*1024*1024:raise HTTPException(502,"display response too large")
    return Response(body if request.method!="HEAD" else b"",status_code=status,media_type=content_type.split(";",1)[0],headers={"Cache-Control":"no-store" if content_type.startswith(("text/html","application/json")) else "private, max-age=300","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer"})
