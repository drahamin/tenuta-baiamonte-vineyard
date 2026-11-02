import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from gateway import HOST, create_app, validate_assets


class EdgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []
        async def upstream(request):
            self.seen.append((request.path, dict(request.headers), await request.read()))
            return web.json_response({"ok": True})
        origin = web.Application()
        origin.router.add_route("*", "/{tail:.*}", upstream)
        self.origin = TestServer(origin)
        await self.origin.start_server()
        self.client = TestClient(TestServer(create_app(["/frontend_latest/test.js"], upstream=str(self.origin.make_url("")).rstrip("/"))), headers={"CF-Connecting-IP": "203.0.113.1"})
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.origin.close()

    async def test_closed_route_matrix_never_reaches_core(self):
        for path in ("/", "/api/websocket", "/api/states", "/api/services/light/turn_on", "/config", "/lovelace", "/hassio", "/supervisor", "/local/secrets", "/static/unlisted.js", "/frontend_latest/unlisted.js", "/api/baiamonte_mobile/v1/energy/extra"):
            response = await self.client.get(path, headers={"Host": HOST})
            self.assertEqual(response.status, 404, path)
        self.assertEqual(self.seen, [])

    async def test_methods_host_upgrade_and_body_are_bounded(self):
        for method, path, headers, data, expected in (
            ("POST", "/api/baiamonte_mobile/v1/energy", {"Host": HOST}, None, 405),
            ("GET", "/auth/authorize", {"Host": "other.example"}, None, 404),
            ("GET", "/auth/authorize", {"Host": HOST, "Upgrade": "websocket"}, None, 404),
            ("POST", "/auth/token", {"Host": HOST}, b"x" * 65537, 413),
            ("GET", "/auth/authorize", {"Host": HOST}, b"x", 400),
        ):
            response = await self.client.request(method, path, headers=headers, data=data)
            self.assertEqual(response.status, expected)
        self.assertEqual(self.seen, [])

    async def test_spoofed_identity_is_removed_and_authorization_preserved(self):
        response = await self.client.post("/api/baiamonte_mobile/v1/session/exchange", headers={"Host": HOST, "Authorization": "Bearer fixture", "X-Remote-User-Id": "forged", "X-Ingress-Path": "forged", "X-Baiamonte-Mobile-Signature": "forged", "Forwarded": "forged", "X-Forwarded-For": "forged"})
        self.assertEqual(response.status, 200)
        headers = {k.lower(): v for k, v in self.seen[-1][1].items()}
        self.assertEqual(headers["authorization"], "Bearer fixture")
        self.assertFalse(any(k.startswith(("x-remote-", "x-ingress-", "x-baiamonte-", "x-forwarded-")) or k == "forwarded" for k in headers))
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_frozen_assets_only(self):
        response = await self.client.get("/frontend_latest/test.js", headers={"Host": HOST})
        self.assertEqual(response.status, 200)
        with self.assertRaises(ValueError):
            validate_assets(["/static/../secrets"])

    async def test_abusive_client_does_not_exhaust_other_clients(self):
        for _ in range(120):
            response = await self.client.get("/auth/authorize", headers={"Host": HOST})
            await response.read()
            self.assertEqual(response.status, 200)
        for _ in range(3):
            response = await self.client.get("/auth/authorize", headers={"Host": HOST})
            self.assertEqual(response.status, 429)
        response = await self.client.get("/auth/authorize", headers={"Host": HOST, "CF-Connecting-IP": "203.0.113.2"})
        self.assertEqual(response.status, 200)
        response = await self.client.get("/auth/authorize", headers={"Host": HOST, "CF-Connecting-IP": "invalid"})
        self.assertEqual(response.status, 403)

    async def test_observed_login_bootstrap_routes_are_read_only(self):
        for path in ("/auth/providers", "/manifest.json"):
            response = await self.client.get(path, headers={"Host": HOST})
            self.assertEqual(response.status, 200)
            response = await self.client.post(path, headers={"Host": HOST})
            self.assertEqual(response.status, 405)


if __name__ == "__main__":
    unittest.main()
