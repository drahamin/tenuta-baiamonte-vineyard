"""Pure, unwired station-weather DTO preparation. No I/O or authority creation.

Only a separately qualified estate-scoped observation may reach this mapper.
Legacy display/cache timestamps are not measurement-clock evidence. Forecast
rows retain the seven field names already consumed by the native direct UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
from uuid import UUID


CONTRACT = "baiamonte.mobile-weather.v1"
SOURCE_OBJECT = "weather_observations"
STALE_AFTER_SECONDS = 3600
_ROLES = frozenset({"admin", "enologist", "worker", "viewer"})


class WeatherProjectionForbidden(ValueError):
    """Caller lacks the existing weather permission."""


@dataclass(frozen=True)
class WeatherReadEvidence:
    """Trusted adapter evidence, never caller-supplied request parameters.

    The shared-clock flag requires proof that observed_at actually dates all
    supplied metrics, not the maximum update time across unrelated HA entities.
    Existing naive DATETIME values need separate historical clock qualification.
    """

    estate_boundary_verified: bool = False
    permitted_columns_verified: bool = False
    observation_clock_verified: bool = False
    shared_metric_clock_verified: bool = False
    measurement_kind: str | None = None
    source_generated_at: datetime | None = None
    last_success_at: datetime | None = None
    fetched_at: datetime | None = None
    source_state: str = "unavailable"


@dataclass(frozen=True)
class ForecastReadEvidence:
    """Qualification from the already-authorized estate weather adapter.

    Unit declarations must come from the selected provider, not a user guess.
    A forecast validity date never establishes when the forecast was issued.
    """

    estate_id: str | None = None
    source_verified: bool = False
    temperature_unit: str | None = None
    precipitation_unit: str | None = None
    wind_speed_unit: str | None = None
    issued_at: datetime | None = None
    last_success_at: datetime | None = None


_CONDITIONS = frozenset({
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
})


def project_native_forecast(rows: object, estate_id: str, clock: datetime,
                            evidence: ForecastReadEvidence) -> tuple[list[dict], dict]:
    qualified = evidence.source_verified is True and evidence.estate_id == estate_id
    issued, succeeded = _time(evidence.issued_at), _time(evidence.last_success_at)
    issued = issued if qualified and issued and issued <= clock else None
    succeeded = succeeded if qualified and succeeded and succeeded <= clock else None
    result = []
    # Bounded input as well as output; no unbounded generator or caller limits.
    for row in (rows[:7] if qualified and isinstance(rows, (list, tuple)) else ()):
        if not isinstance(row, Mapping):
            continue
        valid = _time(row.get("datetime"))
        # The existing UI cannot represent an unknown validity time. Omit that
        # row rather than invent midnight or replace it with fetch/issue time.
        if valid is None:
            continue
        condition = row.get("condition")
        result.append({
            "datetime": _iso(valid),
            "condition": condition if isinstance(condition, str) and condition in _CONDITIONS else None,
            "temperature": _number(row.get("temperature"), -100, 70)
                if evidence.temperature_unit == "celsius" else None,
            "templow": _number(row.get("templow"), -100, 70)
                if evidence.temperature_unit == "celsius" else None,
            "precipitation": _number(row.get("precipitation"), 0, 10000)
                if evidence.precipitation_unit == "millimetres" else None,
            "precipitation_probability": _number(row.get("precipitation_probability"), 0, 100),
            "wind_speed": _number(row.get("wind_speed"), 0, 500)
                if evidence.wind_speed_unit == "kilometres_per_hour" else None,
        })
    age = (clock - issued).total_seconds() if issued else None
    current = bool(result and age is not None and age <= STALE_AFTER_SECONDS and succeeded
                   and (clock - succeeded).total_seconds() <= STALE_AFTER_SECONDS)
    return result, {
        "source_generated_at": _iso(issued), "last_success_at": _iso(succeeded),
        "data_age_seconds": int(age) if age is not None else None,
        "stale": not current,
        "state": "current" if current else "degraded" if result else "unavailable",
    }


def _time(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _number(value: object, lower: float, upper: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = float(Decimal(str(value)))
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and lower <= result <= upper else None


def project_station_weather(
    observation: Mapping[str, object] | None,
    *,
    estate_id: str,
    role: str,
    capabilities: frozenset[str],
    now: datetime,
    evidence: WeatherReadEvidence = WeatherReadEvidence(),
    forecast_rows: object = None,
    forecast_evidence: ForecastReadEvidence = ForecastReadEvidence(),
) -> dict:
    """Project one qualified reporting observation; never fetch or refresh it.

    All unqualified, foreign-estate, malformed-clock and forecast-only input
    fails closed to typed null values. Unknown or untrusted dates are not filled
    from fetch/cache/response times. No notes, entity IDs or advisory text escape.
    """
    if role not in _ROLES or "weather" not in capabilities:
        raise WeatherProjectionForbidden("Weather capability required")
    try:
        if not isinstance(estate_id, str) or str(UUID(estate_id)) != estate_id:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Canonical estate UUID required") from None
    clock = _time(now)
    if clock is None:
        raise ValueError("Aware current clock required")

    row = observation if isinstance(observation, Mapping) else {}
    qualified = all((
        evidence.estate_boundary_verified is True,
        evidence.permitted_columns_verified is True,
        evidence.observation_clock_verified is True,
        evidence.shared_metric_clock_verified is True,
        evidence.measurement_kind in {"measured", "nearby_observation"},
        row.get("estate_id") == estate_id,
        row.get("source_object") == SOURCE_OBJECT,
    ))
    observed = _time(row.get("observed_at")) if qualified else None
    if observed is not None and observed > clock:
        observed = None
    usable = qualified and observed is not None
    temperature = _number(row.get("temp_c"), -100, 70) if usable else None
    rain = _number(row.get("rain_rate_mm_h"), 0, 2000) if usable else None
    wind = _number(row.get("wind_kph"), 0, 500) if usable else None
    gust = _number(row.get("wind_gust_kph"), 0, 500) if usable else None
    has_values = any(value is not None for value in (temperature, rain, wind, gust))
    elapsed = (clock - observed).total_seconds() if observed else None
    age = int(elapsed) if elapsed is not None else None

    def past(value: object) -> datetime | None:
        result = _time(value)
        return result if result is not None and result <= clock else None

    generated = past(evidence.source_generated_at)
    succeeded = past(evidence.last_success_at)
    fetched = past(evidence.fetched_at)
    fresh = bool(has_values and elapsed is not None and elapsed <= STALE_AFTER_SECONDS
                 and evidence.source_state == "current" and generated and succeeded
                 and (clock - generated).total_seconds() <= STALE_AFTER_SECONDS
                 and (clock - succeeded).total_seconds() <= STALE_AFTER_SECONDS)
    state = "current" if fresh else "stale" if has_values else "unavailable"
    forecast, forecast_source = project_native_forecast(forecast_rows, estate_id, clock, forecast_evidence)
    return {
        "contract": CONTRACT,
        "estate_id": estate_id,
        "source": {
            "source_generated_at": _iso(generated),
            "last_success_at": _iso(succeeded),
            "data_age_seconds": age,
            "stale": not fresh,
            "state": "current" if fresh else "degraded" if has_values else "unavailable",
        },
        "weather": {
            "state": state,
            "measurement_kind": evidence.measurement_kind if qualified else None,
            "temperature": {"value": temperature, "unit": "celsius"},
            "condition": None,
            "rain": {"value": rain, "unit": "millimetres_per_hour"},
            "wind": {"speed": wind, "gust": gust, "unit": "kilometres_per_hour"},
            "observed_at": _iso(observed),
            "valid_at": None,
            "fetched_at": _iso(fetched),
            "stale_after_seconds": STALE_AFTER_SECONDS,
        },
        "forecast": forecast,
        "forecast_source": forecast_source,
    }
