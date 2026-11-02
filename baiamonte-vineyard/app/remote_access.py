"""Read-only remote profiles. No policy, identity or permission is provisioned here.

An origin secret authenticates a connector, NOT its end user/device. Every
request additionally requires an RS256 Access assertion for the exact app.
Local revocation applies on the next request: policy is reread every time.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.request
from uuid import UUID

import jwt
from fastapi import HTTPException


POLICY_PATH = Path("/data/remote-access-policy.json")
_ISSUER = re.compile(r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com")
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_NAME = re.compile(r"[A-Za-z0-9_-]{1,128}")
_AUDIENCE = re.compile(r"[a-f0-9]{64}")
_SURFACES = {"labels": "label_device", "field": "field_reader", "pos": "pos_reader"}
_RESOURCE_KEYS = {"labels": {"tank_ids", "kiosk_ids"}, "field": {"task_ids"}, "pos": {"catalog_ids"}}


@dataclass(frozen=True)
class RemoteProfile:
    principal: str
    device_id: str
    surface: str
    role: str
    resources: dict[str, frozenset[str]]

    def require(self, kind: str, resource_id: str) -> None:
        if resource_id not in self.resources.get(kind, frozenset()):
            raise HTTPException(404, "not found")


def resource_id(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(404, "not found") from error
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def load_policy(path: Path = POLICY_PATH) -> dict:
    """Missing, symlinked, broad-mode, malformed or disabled policy denies all."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
                raise ValueError("private policy required")
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise ValueError("policy too large")
        value = json.loads(raw, object_pairs_hook=_unique_object)
        if set(value) != {"schema", "enabled", "issuer", "applications", "profiles"} or type(value["schema"]) is not int or value["schema"] != 1 or value["enabled"] is not True:
            raise ValueError("disabled or invalid policy")
        if not isinstance(value["issuer"], str) or not _ISSUER.fullmatch(value["issuer"]):
            raise ValueError("invalid issuer")
        apps = value["applications"]
        if not isinstance(apps, dict) or not apps or not set(apps) <= set(_SURFACES):
            raise ValueError("invalid applications")
        hosts, audiences = set(), set()
        for app in apps.values():
            if not isinstance(app, dict) or set(app) != {"host", "audience"} or not isinstance(app["host"], str) or not _HOST.fullmatch(app["host"]) or ".." in app["host"]:
                raise ValueError("invalid host")
            if not isinstance(app["audience"], str) or not _AUDIENCE.fullmatch(app["audience"]) or app["host"] in hosts or app["audience"] in audiences:
                raise ValueError("applications must be isolated")
            hosts.add(app["host"])
            audiences.add(app["audience"])
        profiles = value["profiles"]
        if not isinstance(profiles, list) or len(profiles) > 128:
            raise ValueError("invalid profiles")
        identities, devices = set(), set()
        for profile in profiles:
            if not isinstance(profile, dict) or set(profile) != {"principal", "device_id", "surface", "role", "enabled", "expires_at", "resources"}:
                raise ValueError("invalid profile")
            surface = profile["surface"]
            if surface not in apps or profile["role"] != _SURFACES[surface] or type(profile["enabled"]) is not bool:
                raise ValueError("invalid role")
            if not isinstance(profile["principal"], str) or not _NAME.fullmatch(profile["principal"]) or not isinstance(profile["device_id"], str) or not _NAME.fullmatch(profile["device_id"]):
                raise ValueError("invalid identity")
            identity = (surface, profile["principal"])
            if identity in identities or profile["device_id"] in devices or type(profile["expires_at"]) is not int:
                raise ValueError("ambiguous identity")
            identities.add(identity)
            devices.add(profile["device_id"])
            resources = profile["resources"]
            if not isinstance(resources, dict) or set(resources) != _RESOURCE_KEYS[surface]:
                raise ValueError("invalid resources")
            for ids in resources.values():
                if not isinstance(ids, list) or len(ids) > 128 or len(set(ids)) != len(ids):
                    raise ValueError("invalid resource set")
                for item in ids:
                    resource_id(item)
        return value
    except (OSError, ValueError, TypeError, KeyError, HTTPException) as error:
        raise HTTPException(503, "remote access unavailable") from error


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_jwks(issuer: str) -> dict:
    """Only a policy-pinned Cloudflare HTTPS issuer; never JWT jku/x5u URLs.

    No stale cache fallback: inability to verify current keys denies access.
    The small dedicated pilot intentionally trades availability for revocation.
    """
    if not _ISSUER.fullmatch(issuer):
        raise ValueError("invalid issuer")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    request = urllib.request.Request(issuer + "/cdn-cgi/access/certs", headers={"Accept": "application/json"})
    with opener.open(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError("keys unavailable")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("keys too large")
    return json.loads(raw, object_pairs_hook=_unique_object)


def authorize_remote(host: str, surface: str, assertion: str | None) -> RemoteProfile:
    policy = load_policy()
    app = policy["applications"].get(surface)
    if app is None or host != app["host"]:
        raise HTTPException(404, "not found")
    if not isinstance(assertion, str) or not 1 <= len(assertion) <= 16384:
        raise HTTPException(401, "authentication required")
    try:
        header = jwt.get_unverified_header(assertion)
        if set(header) - {"alg", "kid", "typ"} or header.get("alg") != "RS256" or header.get("typ", "JWT") != "JWT" or not isinstance(header.get("kid"), str) or not _NAME.fullmatch(header["kid"]):
            raise ValueError("invalid header")
        keys = fetch_jwks(policy["issuer"]).get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
            raise ValueError("invalid keys")
        matches = [key for key in keys if isinstance(key, dict) and key.get("kid") == header["kid"]]
        if len(matches) != 1:
            raise ValueError("unknown or ambiguous key")
        key = matches[0]
        if key.get("kty") != "RSA" or key.get("use", "sig") != "sig" or key.get("alg", "RS256") != "RS256" or "d" in key:
            raise ValueError("invalid signing key")
        public_key = jwt.PyJWK.from_dict(key, algorithm="RS256").key
        if not 2048 <= public_key.key_size <= 8192:
            raise ValueError("weak key")
        claims = jwt.decode(assertion, public_key, algorithms=["RS256"], issuer=policy["issuer"], audience=app["audience"], options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        now = time.time()
        if type(claims["exp"]) is not int or type(claims["iat"]) is not int or claims["exp"] <= claims["iat"] or claims["exp"] - claims["iat"] > 86400 or claims["iat"] > now:
            raise ValueError("invalid lifetime")
        # No caller email/role/device header is used as authorization evidence.
        profile = next((p for p in policy["profiles"] if p["surface"] == surface and p["principal"] == claims["sub"] and p["enabled"] and p["expires_at"] > now), None)
        if profile is None:
            raise ValueError("identity not provisioned")
        return RemoteProfile(profile["principal"], profile["device_id"], surface, profile["role"], {key: frozenset(ids) for key, ids in profile["resources"].items()})
    except Exception as error:
        # Never return assertions, key material, profile values or upstream URLs.
        raise HTTPException(401, "authentication required") from error
