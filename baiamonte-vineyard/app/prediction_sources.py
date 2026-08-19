"""Credential-free external evidence for vineyard prediction models.

Each source has a narrow role.  None is authoritative for a picking date and
none can overwrite observations, laboratory results, or an approved plan.
"""

from __future__ import annotations

import ast
import array
import json
import math
import statistics
import struct
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .config import get_settings, runtime_option
from .db import fetch_all, fetch_one, transaction
from .prediction_refresh import request_harvest_refresh
from .service import estate_id, json_ready


ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
SIAS_PACKAGE_URL = "https://dati.regione.sicilia.it/api/3/action/package_show?id=73146754-9877-4a4c-8ae7-b5b7385be81f"
SENTINEL_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SENTINEL_DATA_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/feature.npy"

SOURCE_ROLES = {
    "open_meteo_ensemble": "near_term_uncertainty",
    "sias_validation": "independent_validation_only",
    "sentinel_2_vegetation": "block_vegetation_trend_only",
    "ecmwf_seasonal": "early_planning_only",
}


def _json_request(url: str, *, payload: dict[str, Any] | None = None, timeout: int = 45) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Tenuta-Baiamonte-Prediction/1.0"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _bytes_request(url: str, payload: dict[str, Any], timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Accept": "application/octet-stream", "Content-Type": "application/json", "User-Agent": "Tenuta-Baiamonte-Prediction/1.0"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_npy_cube(content: bytes) -> tuple[tuple[int, ...], list[float]]:
    """Read the small, uncompressed NPY cubes returned by TiTiler."""
    if not content.startswith(b"\x93NUMPY") or len(content) < 12:
        raise ValueError("Sentinel processor did not return an NPY cube")
    major = content[6]
    if major == 1:
        header_length, offset = struct.unpack("<H", content[8:10])[0], 10
    else:
        header_length, offset = struct.unpack("<I", content[8:12])[0], 12
    header = ast.literal_eval(content[offset:offset + header_length].decode("latin1").strip())
    if header.get("fortran_order"):
        raise ValueError("Fortran-ordered Sentinel arrays are unsupported")
    descriptor = str(header.get("descr") or "")
    typecode = {"<u2": "H", "<i2": "h", "<f4": "f", "<f8": "d"}.get(descriptor)
    if not typecode:
        raise ValueError(f"Unsupported Sentinel array type {descriptor}")
    values = array.array(typecode)
    values.frombytes(content[offset + header_length:])
    if values.itemsize > 1 and struct.pack("=H", 1) != struct.pack("<H", 1):
        values.byteswap()
    return tuple(int(value) for value in header["shape"]), [float(value) for value in values]


def sentinel_index_statistics(content: bytes) -> dict[str, Any]:
    shape, values = parse_npy_cube(content)
    if len(shape) != 3 or shape[0] < 6:
        raise ValueError("Sentinel cube must contain B02, B04, B05, B08, SCL and mask")
    _, height, width = shape
    pixels = height * width
    blue, red, red_edge, nir, scl, mask = [values[index * pixels:(index + 1) * pixels] for index in range(6)]
    ndvi_values, ndre_values, lai_values = [], [], []
    for index in range(pixels):
        if mask[index] <= 0 or int(round(scl[index])) not in {4, 5}:
            continue
        b, r, re, n = blue[index] / 10000, red[index] / 10000, red_edge[index] / 10000, nir[index] / 10000
        if n + r <= 0 or n + re <= 0:
            continue
        ndvi = (n - r) / (n + r)
        ndre = (n - re) / (n + re)
        evi_denominator = n + 6 * r - 7.5 * b + 1
        evi = 2.5 * (n - r) / evi_denominator if abs(evi_denominator) > .0001 else None
        if -1 <= ndvi <= 1 and -1 <= ndre <= 1:
            ndvi_values.append(ndvi)
            ndre_values.append(ndre)
            if evi is not None:
                # Empirical EVI-derived LAI estimate; intentionally not
                # represented as an ESA biophysical Level-2 product.
                lai_values.append(max(0.0, min(8.0, 3.618 * evi - .118)))
    def stats(values: list[float]) -> dict[str, float | None]:
        return {"mean": round(statistics.mean(values), 4) if values else None, "p10": round(_percentile(values, .10), 4) if values else None, "p90": round(_percentile(values, .90), 4) if values else None}
    return {"valid_pixels": len(ndvi_values), "total_pixels": pixels, "valid_fraction": round(len(ndvi_values) / pixels, 3) if pixels else 0, "ndvi": stats(ndvi_values), "ndre": stats(ndre_values), "lai_estimate": stats(lai_values), "lai_method": "3.618 × EVI − 0.118, clipped 0–8; empirical estimate, not an ESA Level-2 LAI product"}


def _geometry_points(value: Any) -> list[tuple[float, float]]:
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: return []
    coordinates = value.get("coordinates") if isinstance(value, dict) else None
    points: list[tuple[float, float]] = []
    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(part, (int, float)) for part in node[:2]):
            points.append((float(node[0]), float(node[1])))
        elif isinstance(node, (list, tuple)):
            for child in node: walk(child)
    walk(coordinates)
    return points


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_ensemble(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce hourly members to daily probabilities and honest spread."""
    hourly = payload.get("hourly") or {}
    times = list(hourly.get("time") or [])
    member_keys = sorted(key for key in hourly if key.startswith("precipitation_member"))
    temperature_keys = sorted(key for key in hourly if key.startswith("temperature_2m_member"))
    days: dict[str, dict[str, list[list[float]]]] = {}
    for index, stamp in enumerate(times):
        day = str(stamp)[:10]
        bucket = days.setdefault(day, {"rain": [[] for _ in member_keys], "temperature": [[] for _ in temperature_keys]})
        for member_index, key in enumerate(member_keys):
            values = hourly.get(key) or []
            if index < len(values) and values[index] is not None:
                bucket["rain"][member_index].append(float(values[index]))
        for member_index, key in enumerate(temperature_keys):
            values = hourly.get(key) or []
            if index < len(values) and values[index] is not None:
                bucket["temperature"][member_index].append(float(values[index]))
    daily = []
    for day, values in sorted(days.items()):
        rain_members = [sum(member) for member in values["rain"] if member]
        high_members = [max(member) for member in values["temperature"] if member]
        daily.append({
            "date": day,
            "members": max(len(rain_members), len(high_members)),
            "rain_mm_p10": _percentile(rain_members, .10),
            "rain_mm_median": _percentile(rain_members, .50),
            "rain_mm_p90": _percentile(rain_members, .90),
            "rain_probability_5mm_pct": round(sum(value >= 5 for value in rain_members) / len(rain_members) * 100, 1) if rain_members else None,
            "high_c_p10": _percentile(high_members, .10),
            "high_c_median": _percentile(high_members, .50),
            "high_c_p90": _percentile(high_members, .90),
            "heat_probability_35c_pct": round(sum(value >= 35 for value in high_members) / len(high_members) * 100, 1) if high_members else None,
        })
    return {"model": payload.get("model") or "ecmwf_ifs025", "member_count": max([row["members"] for row in daily] or [0]), "days": daily}


def summarize_seasonal(payload: dict[str, Any]) -> dict[str, Any]:
    daily = payload.get("daily") or {}
    times = list(daily.get("time") or [])
    result = []
    for index, stamp in enumerate(times):
        temperatures = [float(values[index]) for key, values in daily.items() if key.startswith("temperature_2m_mean_member") and isinstance(values, list) and index < len(values) and values[index] is not None]
        rain = [float(values[index]) for key, values in daily.items() if key.startswith("precipitation_sum_member") and isinstance(values, list) and index < len(values) and values[index] is not None]
        mean_temperatures = daily.get("temperature_2m_mean") or []
        mean_rain = daily.get("precipitation_sum") or []
        if not temperatures and index < len(mean_temperatures) and mean_temperatures[index] is not None:
            temperatures = [float(mean_temperatures[index])]
        if not rain and index < len(mean_rain) and mean_rain[index] is not None:
            rain = [float(mean_rain[index])]
        row: dict[str, Any] = {
            "date": stamp,
            "temperature_c_p10": _percentile(temperatures, .10),
            "temperature_c_median": _percentile(temperatures, .50),
            "temperature_c_p90": _percentile(temperatures, .90),
            "rain_mm_p10": _percentile(rain, .10),
            "rain_mm_median": _percentile(rain, .50),
            "rain_mm_p90": _percentile(rain, .90),
            "members": max(len(temperatures), len(rain)),
        }
        result.append(row)
    return {"model": payload.get("model") or "ecmwf_seasonal_seamless", "daily": result}


def _location_queries_enabled() -> bool:
    return bool(runtime_option("external_public_location_queries_enabled", get_settings().external_public_location_queries_enabled))


def _waiting_location_permission(source_code: str, url: str) -> dict[str, Any]:
    payload = {"free": True, "credentials_required": False, "location_transmitted": False, "privacy_gate": "waiting for explicit owner approval to send estate coordinates to this public service"}
    _store(source_code, "waiting_for_opt_in", payload, observed_at=datetime.now(timezone.utc), source_url=url)
    return {"status": "waiting_for_opt_in", **payload}


def _store(source_code: str, status: str, payload: dict[str, Any], *, role: str | None = None, scope_type: str = "estate", scope_id: str = "estate", observed_at: datetime | None = None, valid_from: date | None = None, valid_through: date | None = None, source_url: str | None = None, error: str | None = None) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO prediction_source_snapshots (estate_id,source_code,scope_type,scope_id,status,role_code,observed_at,valid_from,valid_through,payload,source_url,error_message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (estate_id(), source_code, scope_type, scope_id, status, role or SOURCE_ROLES[source_code], observed_at, valid_from, valid_through, json.dumps(json_ready(payload)), source_url, (error or "")[:500] or None),
        )


def _estate_location() -> tuple[float, float]:
    row = fetch_one("SELECT latitude,longitude FROM estates WHERE id=%s", (estate_id(),)) or {}
    return float(row.get("latitude") or 37.8464), float(row.get("longitude") or 14.9247)


def refresh_ensemble() -> dict[str, Any]:
    if not _location_queries_enabled():
        return _waiting_location_permission("open_meteo_ensemble", ENSEMBLE_URL)
    latitude, longitude = _estate_location()
    query = urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude, "hourly": "temperature_2m,precipitation",
        "models": "ecmwf_ifs025", "forecast_days": 15, "timezone": "Europe/Rome",
    })
    payload = summarize_ensemble(_json_request(f"{ENSEMBLE_URL}?{query}"))
    days = payload.get("days") or []
    status = "fresh" if days and payload.get("member_count") else "no_data"
    _store("open_meteo_ensemble", status, payload, observed_at=datetime.now(timezone.utc), valid_from=date.fromisoformat(days[0]["date"]) if days else None, valid_through=date.fromisoformat(days[-1]["date"]) if days else None, source_url=ENSEMBLE_URL)
    return {"status": status, **payload}


def refresh_seasonal() -> dict[str, Any]:
    if not _location_queries_enabled():
        return _waiting_location_permission("ecmwf_seasonal", SEASONAL_URL)
    latitude, longitude = _estate_location()
    query = urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude,
        "daily": "temperature_2m_mean,precipitation_sum",
        "forecast_days": 210, "timezone": "Europe/Rome",
    })
    payload = summarize_seasonal(_json_request(f"{SEASONAL_URL}?{query}"))
    days = payload.get("daily") or []
    climatology = {int(row["month_number"]): row for row in fetch_all("SELECT MONTH(weather_date) month_number,AVG(temp_avg_c) temp_c,SUM(rain_mm)/COUNT(DISTINCT YEAR(weather_date)) rain_mm,COUNT(DISTINCT YEAR(weather_date)) baseline_years FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date)<YEAR(CURDATE()) GROUP BY MONTH(weather_date)", (estate_id(),))}
    monthly: dict[str, dict[str, Any]] = {}
    for row in days:
        month = str(row["date"])[:7]
        bucket = monthly.setdefault(month, {"month": month, "temperatures": [], "rain": []})
        if row.get("temperature_c_median") is not None: bucket["temperatures"].append(float(row["temperature_c_median"]))
        if row.get("rain_mm_median") is not None: bucket["rain"].append(float(row["rain_mm_median"]))
    anomalies = []
    for month, bucket in sorted(monthly.items()):
        baseline = climatology.get(int(month[-2:])) or {}
        temperature = statistics.mean(bucket["temperatures"]) if bucket["temperatures"] else None
        rain = sum(bucket["rain"]) if bucket["rain"] else None
        anomalies.append({"month": month, "forecast_temperature_c": temperature, "forecast_rain_mm": rain, "local_temperature_anomaly_c": temperature - float(baseline["temp_c"]) if temperature is not None and baseline.get("temp_c") is not None else None, "local_rain_anomaly_mm": rain - float(baseline["rain_mm"]) if rain is not None and baseline.get("rain_mm") is not None else None, "baseline_years": int(baseline.get("baseline_years") or 0), "baseline": "MariaDB observed monthly average before current year; limited available-year baseline, not a 30-year climate normal"})
    payload = {"model": payload.get("model"), "forecast_days": len(days), "member_count": max([int(row.get("members") or 0) for row in days] or [0]), "monthly_anomalies": anomalies}
    payload["planning_limit"] = "36-km area outlook for early planning only; prohibited from selecting or moving an exact picking date."
    status = "fresh" if days else "no_data"
    _store("ecmwf_seasonal", status, payload, observed_at=datetime.now(timezone.utc), valid_from=date.fromisoformat(days[0]["date"]) if days else None, valid_through=date.fromisoformat(days[-1]["date"]) if days else None, source_url=SEASONAL_URL)
    return {"status": status, **payload}


def refresh_sias() -> dict[str, Any]:
    """Read the anonymous Regione Siciliana open-data catalog.

    The catalog currently describes non-validated station exports.  It is
    independent validation only and is never substituted for the GW2000.
    """
    try:
        catalog = _json_request(SIAS_PACKAGE_URL)
    except Exception as error:
        payload = {"dataset": "SIAS - Precipitazioni", "publisher": "Regione Siciliana", "latest_public_catalog_period": "2022", "validation_only": True, "current_validation_available": False, "warning": "The anonymous regional open-data catalog is historical and its publisher endpoint is presently unavailable; it is not substituted with a credentialed feed."}
        _store("sias_validation", "historical_catalog_only", payload, observed_at=datetime.now(timezone.utc), source_url="https://www.dati.gov.it/node/view-dataset/dataset?id=63be93a5-d3a2-4a44-b72f-15e5a7505b02", error=str(error))
        return {"status": "historical_catalog_only", **payload}
    resources = (catalog.get("result") or {}).get("resources") or []
    downloadable = [row for row in resources if str(row.get("format") or "").upper() in {"CSV", "JSON"} and row.get("url")]
    latest = max(downloadable, key=lambda row: str(row.get("last_modified") or row.get("created") or row.get("name") or ""), default=None)
    payload = {
        "dataset": (catalog.get("result") or {}).get("title") or "SIAS regional station data",
        "license": (catalog.get("result") or {}).get("license_title"),
        "resource_count": len(downloadable),
        "latest_resource": {key: latest.get(key) for key in ("name", "format", "url", "last_modified", "created")} if latest else None,
        "validation_only": True,
        "warning": "Regional open-data observations are non-validated and may be published after the live station portal.",
    }
    # This anonymous catalog currently contains historical exports rather than
    # a current station feed.  Calling it simply “available” overstates what it
    # can validate for an operational picking decision.
    payload["latest_public_catalog_period"] = "2022"
    payload["current_validation_available"] = False
    status = "historical_catalog_only" if latest else "no_data"
    _store("sias_validation", status, payload, observed_at=datetime.now(timezone.utc), source_url=SIAS_PACKAGE_URL)
    return {"status": status, **payload}


def refresh_sentinel() -> dict[str, Any]:
    """Protect exact block boundaries unless public processing is opted in."""
    enabled = bool(runtime_option("sentinel_public_processing_enabled", get_settings().sentinel_public_processing_enabled))
    blocks = fetch_all("SELECT id,code,geometry_geojson FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),))
    mapped_blocks = [row for row in blocks if row.get("geometry_geojson")]
    parcels = fetch_all("SELECT id,CONCAT('Parcel ',parcel_number) code,geometry_geojson FROM cadastral_parcels WHERE estate_id=%s ORDER BY parcel_number", (estate_id(),))
    mapped_parcels = [row for row in parcels if row.get("geometry_geojson")]
    mapped = mapped_blocks or mapped_parcels
    geometry_scope = "block" if mapped_blocks else "cadastral_parcel"
    payload = {
        "provider": "Microsoft Planetary Computer / ESA Sentinel-2 L2A",
        "free": True,
        "credentials_required": False,
        "public_processing_enabled": enabled,
        "mapped_blocks": len(mapped_blocks),
        "total_blocks": len(blocks),
        "mapped_parcels": len(mapped_parcels),
        "total_parcels": len(parcels),
        "geometry_scope": geometry_scope if mapped else None,
        "metrics": ["NDVI", "NDRE", "LAI estimate"],
        "model_role": "Trend evidence only; vegetation indices do not directly move an exact harvest date.",
    }
    # Exact geometries are deliberately not transmitted until the owner opts
    # into public processing.  The processor implementation remains isolated
    # here so no other refresh can bypass that privacy gate.
    if not mapped:
        _store("sentinel_2_vegetation", "missing_geometry", payload, observed_at=datetime.now(timezone.utc), source_url=SENTINEL_STAC_URL)
        return {"status": "missing_geometry", **payload}
    if not enabled:
        _store("sentinel_2_vegetation", "waiting_for_opt_in", payload, observed_at=datetime.now(timezone.utc), source_url=SENTINEL_STAC_URL)
        return {"status": "waiting_for_opt_in", **payload}
    all_points = [point for row in mapped for point in _geometry_points(row.get("geometry_geojson"))]
    if not all_points:
        _store("sentinel_2_vegetation", "missing_geometry", payload, observed_at=datetime.now(timezone.utc), source_url=SENTINEL_STAC_URL)
        return {"status": "missing_geometry", **payload}
    end, start = date.today(), date.today() - timedelta(days=75)
    search = _json_request(SENTINEL_STAC_URL, payload={"collections": ["sentinel-2-l2a"], "bbox": [min(point[0] for point in all_points), min(point[1] for point in all_points), max(point[0] for point in all_points), max(point[1] for point in all_points)], "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z", "query": {"eo:cloud_cover": {"lt": 35}}, "sortby": [{"field": "properties.datetime", "direction": "desc"}], "limit": 6})
    scenes = (search.get("features") or [])[:3]
    block_results = []
    for block in mapped:
        geometry = block.get("geometry_geojson")
        if isinstance(geometry, str): geometry = json.loads(geometry)
        observations = []
        for scene in scenes:
            query = urllib.parse.urlencode([("collection", "sentinel-2-l2a"), ("item", scene["id"]), ("assets", "B02"), ("assets", "B04"), ("assets", "B05"), ("assets", "B08"), ("assets", "SCL"), ("asset_as_band", "true"), ("max_size", "128"), ("resampling", "nearest")])
            statistics_payload = sentinel_index_statistics(_bytes_request(f"{SENTINEL_DATA_URL}?{query}", {"type": "Feature", "properties": {}, "geometry": geometry}))
            if statistics_payload["valid_pixels"]:
                observations.append({"scene_id": scene["id"], "observed_at": (scene.get("properties") or {}).get("datetime"), "scene_cloud_cover_pct": (scene.get("properties") or {}).get("eo:cloud_cover"), **statistics_payload})
        observations.sort(key=lambda row: str(row.get("observed_at") or ""))
        trend = {}
        if len(observations) >= 2:
            for metric in ("ndvi", "ndre", "lai_estimate"):
                first, latest = observations[0][metric]["mean"], observations[-1][metric]["mean"]
                trend[f"{metric}_change"] = round(latest - first, 4) if first is not None and latest is not None else None
        block_payload = {"block_code": block.get("code"), "observations": observations, "trend": trend, "trend_role": "vigor/stress evidence only; no direct exact-date adjustment"}
        block_status = "fresh" if observations else "no_clear_pixels"
        _store("sentinel_2_vegetation", block_status, block_payload, scope_type=geometry_scope, scope_id=str(block["id"]), observed_at=datetime.now(timezone.utc), valid_from=date.fromisoformat(str(observations[0]["observed_at"])[:10]) if observations else None, valid_through=date.fromisoformat(str(observations[-1]["observed_at"])[:10]) if observations else None, source_url=SENTINEL_STAC_URL)
        block_results.append({"block_id": block["id"], "status": block_status, **block_payload})
    status = "fresh" if any(row["status"] == "fresh" for row in block_results) else "no_clear_pixels"
    payload["blocks"] = block_results
    _store("sentinel_2_vegetation", status, payload, observed_at=datetime.now(timezone.utc), source_url=SENTINEL_STAC_URL)
    return {"status": status, **payload}


def refresh_prediction_sources() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for code, refresh in (
        ("open_meteo_ensemble", refresh_ensemble),
        ("sias_validation", refresh_sias),
        ("sentinel_2_vegetation", refresh_sentinel),
        ("ecmwf_seasonal", refresh_seasonal),
    ):
        try:
            results[code] = refresh()
        except Exception as error:
            _store(code, "failed", {"role": SOURCE_ROLES[code]}, observed_at=datetime.now(timezone.utc), error=str(error))
            results[code] = {"status": "failed", "error": str(error)[:300]}
    forecast_status = (results.get("open_meteo_ensemble") or {}).get("status")
    if forecast_status == "fresh":
        request_harvest_refresh("external_prediction_sources", datetime.now(timezone.utc).strftime("%Y%m%d%H"), "Fresh ensemble uncertainty evidence is available")
    return {"status": "processed", "sources": results, "credential_policy": "free_without_credentials_only"}


def prediction_source_context() -> dict[str, Any]:
    rows = fetch_all(
        "SELECT p.source_code,p.scope_type,p.scope_id,p.status,p.role_code,p.observed_at,p.valid_from,p.valid_through,p.payload,p.source_url,p.error_message,p.created_at FROM prediction_source_snapshots p JOIN (SELECT source_code,scope_type,scope_id,MAX(id) id FROM prediction_source_snapshots WHERE estate_id=%s GROUP BY source_code,scope_type,scope_id) latest ON latest.id=p.id ORDER BY p.source_code,(p.scope_type='estate') DESC,p.scope_id",
        (estate_id(),),
    )
    result: dict[str, Any] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try: payload = json.loads(payload)
            except ValueError: payload = {}
        code = str(row["source_code"])
        prepared = {**row, "payload": payload}
        if row.get("scope_type") == "estate":
            scopes = (result.get(code) or {}).get("scopes") or []
            result[code] = {**prepared, "scopes": scopes}
        else:
            result.setdefault(code, {"source_code": code, "status": "scope_only", "role_code": row.get("role_code"), "payload": {}, "scopes": []})["scopes"].append(prepared)
    return result


def ensemble_pick_window_adjustment(context: dict[str, Any], predicted: date, today: date) -> tuple[int, dict[str, Any]]:
    """Return a bounded adjustment only when the ensemble overlaps picking."""
    source = context.get("open_meteo_ensemble") or {}
    if source.get("status") != "fresh" or predicted > today + timedelta(days=15):
        return 0, {"applied": False, "reason": "forecast horizon does not overlap predicted picking date"}
    days = (source.get("payload") or {}).get("days") or []
    window = [row for row in days if abs((date.fromisoformat(row["date"]) - predicted).days) <= 1]
    wet_probability = max([float(row.get("rain_probability_5mm_pct") or 0) for row in window] or [0])
    heat_probability = max([float(row.get("heat_probability_35c_pct") or 0) for row in window] or [0])
    adjustment = 1 if wet_probability >= 60 else -1 if heat_probability >= 60 else 0
    return adjustment, {"applied": bool(adjustment), "rain_probability_5mm_pct": wet_probability, "heat_probability_35c_pct": heat_probability, "bounded_adjustment_days": adjustment, "rule": "±1 day only at >=60% ensemble probability; agronomist approval remains required"}
