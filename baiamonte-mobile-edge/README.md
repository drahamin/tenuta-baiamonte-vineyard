# Dedicated mobile edge candidate

Default disabled, manual boot, no published ports, host networking or Supervisor/Core API privilege. The only upstream is Core's site-local address. The aiohttp listener binds 127.0.0.1:8184 within the connector container; no LAN client reaches it directly. Connector credential is a dedicated tunnel-only token in private options, materialized as a 0600 token file and never passed on the command line.

Cloudflare ingress must contain exactly `baiamonte.rhmproxy.com -> http://127.0.0.1:8184` and terminal `http_status:404`. No ERP tunnel reuse, wildcard hostname, display route or direct Core/Vineyard target. Remote tunnel ingress must be inspected before the enabled flag is set.

The gateway has explicit route/method checks, rejects upgrades and encoded/ambiguous paths, removes remote identity/proof/forwarded headers, preserves OAuth/app Authorization, bounds request/response sizes and memory/rate buckets, disables access logging and follows no redirects. Static paths require an exact frozen asset list. Asset set must be created from the successful installed-Core login trace and written privately to `/data/login-assets.json`; an absent or empty list prevents connector startup. No asset list or token is included in source.

Not ready for production until: container build and exit behavior pass; fresh review passes; complete login asset trace is frozen; tunnel ingress is independently verified; OAuth/app exchange/revoke and route-denial tests pass locally; only then activate public DNS and test native login/WAN recovery. Core relay is already loaded; this component requires no additional Core restart.

Official connector source: https://github.com/cloudflare/cloudflared/releases/tag/2026.10.7 . ARM64 executable digest is pinned to the official release asset. Cloudflare token-file documentation: https://developers.cloudflare.com/tunnel/reference/run-parameters/ .

Isolated tests: `python -m unittest -q test_gateway`. Tests use a loopback mock upstream and never connect to HA or Cloudflare.
