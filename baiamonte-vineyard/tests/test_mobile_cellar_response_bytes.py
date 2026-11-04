"""Synthetic UTF-8/complete-response regressions; never contact HA or a DB."""
from uuid import UUID
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.domains import mobile_cellar_projection as cellar
from app.domains import mobile_site_routes as routes

ESTATE = "11111111-1111-4111-8111-111111111111"
TANK = "22222222-2222-4222-8222-222222222222"


def source_rows(count, large=False):
    rows = []
    for i in range(count):
        # These lengths meet 001_core.sql: VARCHAR(80), (160), (255).
        code = f"{i:04}" + "🍇" * 76 if large else f"L-{i}"
        rows.append({"container_id": TANK, "container_estate_id": ESTATE,
                     "container_code": "T1", "container_name": "Tank one",
                     "container_type": "tank", "material": "steel", "location": "Cellar",
                     "capacity_l": 1000, "container_status": "in_use",
                     "wine_lot_id": str(UUID(int=i+1)), "lot_estate_id": ESTATE,
                     "season_estate_id": ESTATE, "current_container_id": TANK,
                     "wine_lot_code": code, "wine_lot_name": "🍇" * 160 if large else "Lot",
                     "stage": "aging", "variety_summary": "🍇" * 255 if large else "Nerello",
                     "vintage_year": 2026, "volume_l": 0 if i == 0 else None})
    return rows


class CellarResponseBytes(unittest.TestCase):
    def setUp(self):
        self.rows = source_rows(2)
        self.identity = {"role": "admin", "capabilities": {"records"}}
        for name, value in {"estate_id": lambda: ESTATE,
                            "read_cellar_links": lambda _: cellar.project_cellar_links(self.rows, ESTATE),
                            "read_records": lambda *args: [{"id": TANK, "code": "T1"}]}.items():
            p = patch.object(routes, name, value)
            p.start(); self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.require_records] = lambda: self.identity
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def get(self):
        return self.client.get("/api/v1/mobile/records?object=cellar&projection=cellar-links-v1")

    def test_schema_valid_row_limit_can_exceed_relay_bytes(self):
        rows = source_rows(1000, large=True)
        self.assertEqual(len({r["wine_lot_code"] for r in rows}), 1000)
        self.assertTrue(all(len(r["wine_lot_code"]) == 80 and len(r["wine_lot_name"]) == 160 and len(r["variety_summary"]) == 255 for r in rows))
        items = cellar.project_cellar_links(rows, ESTATE)
        self.assertEqual(len(items[0]["wine_lots"]), 1000)
        self.assertGreater(len(JSONResponse({"items": items}).body), 2 * 1024 * 1024)
        with self.assertRaises(cellar.ReportingSourceUnavailable):
            cellar.enforce_response_byte_limit({"items": items})

    def test_oversized_complete_http_projection_is_small_503_not_partial_200(self):
        self.rows = source_rows(1000, large=True)
        result = self.get()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json(), {"detail": "mobile_reporting_source_unavailable"})
        self.assertLess(len(result.content), 256)

    def test_small_http_projection_is_complete_and_preserves_zero_unknown(self):
        self.rows = source_rows(20)
        result = self.get()
        self.assertEqual(result.status_code, 200)
        payload = result.json()
        self.assertTrue(payload["complete"])
        lots = payload["items"][0]["wine_lots"]
        self.assertEqual(len(lots), 20)
        self.assertEqual(lots[0]["reported_volume_l"], 0)
        self.assertIsNone(lots[1]["reported_volume_l"])
        self.assertLessEqual(len(result.content), cellar.MAX_RESPONSE_BYTES)

    def test_exact_two_mib_boundary_is_inclusive(self):
        overhead = len(JSONResponse({"value": ""}).body)
        payload = {"value": "a" * (cellar.MAX_RESPONSE_BYTES-overhead)}
        self.assertEqual(len(JSONResponse(payload).body), cellar.MAX_RESPONSE_BYTES)
        cellar.enforce_response_byte_limit(payload)
        payload["value"] += "a"
        with self.assertRaises(cellar.ReportingSourceUnavailable):
            cellar.enforce_response_byte_limit(payload)

    def test_utf8_escaping_and_whole_envelope_match_jsonresponse(self):
        payload = {"items": [{"name": "🍇\n\"\\"}], "complete": True, "metadata": {"source": "unknown"}}
        size = len(JSONResponse(payload).body)
        cellar.enforce_response_byte_limit(payload, size)
        with self.assertRaises(cellar.ReportingSourceUnavailable):
            cellar.enforce_response_byte_limit(payload, size-1)
        with self.assertRaises(cellar.ReportingSourceUnavailable):
            cellar.enforce_response_byte_limit(payload, len(JSONResponse(payload["items"]).body))

    def test_legacy_response_and_existing_role_denial_are_unchanged(self):
        result = self.client.get("/api/v1/mobile/records?object=cellar")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("projection_contract", result.json())
        self.identity = {"role": "worker", "capabilities": {"records"}}
        self.assertEqual(self.get().status_code, 403)


if __name__ == "__main__":
    unittest.main()
