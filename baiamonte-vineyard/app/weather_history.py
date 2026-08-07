from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from .db import fetch_one, transaction
from .service import estate_id, new_id


def _number(value: Any) -> float | None:
    try:
        text = str(value).strip()
        return None if not text or text == "-" else float(text)
    except Exception:
        return None


def _weather_date(value: Any):
    text = str(value or "").strip()
    for parser in (
        lambda: datetime.fromisoformat(text),
        lambda: datetime.strptime(text, "%Y-%m-%d %H:%M"),
        lambda: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
        lambda: datetime.strptime(text, "%Y-%m-%d"),
    ):
        try:
            return parser().date()
        except (TypeError, ValueError):
            continue
    return None


def _station(cursor: Any) -> str:
    row = fetch_one("SELECT id FROM weather_stations WHERE estate_id=%s AND external_id='baiamonte-weather-google-sheet'", (estate_id(),))
    if row:
        return row["id"]
    record_id = new_id()
    cursor.execute("INSERT INTO weather_stations (id,estate_id,name,station_type,external_id,location_type,metadata) VALUES (%s,%s,'Baiamonte Weather archive','other','baiamonte-weather-google-sheet','vineyard',JSON_OBJECT('source','Google Drive Baiamonte Weather'))", (record_id, estate_id()))
    return record_id


def import_baiamonte_weather_csv(data: bytes) -> dict[str, int]:
    text = data.decode("utf-8-sig", errors="replace")
    rows = csv.reader(io.StringIO(text))
    next(rows, None)
    imported = skipped = 0
    with transaction() as (_, cursor):
        station_id = _station(cursor)
        for row in rows:
            if len(row) < 41:
                skipped += 1
                continue
            date_index = None
            for candidate in (0, 1):
                weather_date = _weather_date(row[candidate])
                if weather_date is not None:
                    date_index = candidate
                    break
            if date_index is None:
                skipped += 1
                continue
            # The Google Sheets CSV begins with the date in column A. Retain
            # support for the older exported form that included a leading index.
            temp_avg, temp_min, temp_max = _number(row[date_index + 1]), _number(row[date_index + 2]), _number(row[date_index + 3])
            humidity = _number(row[date_index + 6])
            rain = _number(row[date_index + 25])
            wind = _number(row[date_index + 33])
            solar_wm2 = _number(row[date_index + 16])
            solar = solar_wm2 * 0.0864 if solar_wm2 is not None else None
            soil = _number(row[date_index + 40])
            gdd = max(0.0, ((temp_min or temp_avg or 10) + (temp_max or temp_avg or 10)) / 2 - 10)
            cursor.execute(
                "INSERT INTO weather_daily (estate_id,station_id,weather_date,temp_min_c,temp_avg_c,temp_max_c,humidity_avg_pct,rain_mm,wind_max_kph,solar_mj_m2,soil_moisture_avg_pct,gdd_base10) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE temp_min_c=VALUES(temp_min_c),temp_avg_c=VALUES(temp_avg_c),temp_max_c=VALUES(temp_max_c),humidity_avg_pct=VALUES(humidity_avg_pct),rain_mm=VALUES(rain_mm),wind_max_kph=VALUES(wind_max_kph),solar_mj_m2=VALUES(solar_mj_m2),soil_moisture_avg_pct=VALUES(soil_moisture_avg_pct),gdd_base10=VALUES(gdd_base10)",
                (estate_id(), station_id, weather_date, temp_min, temp_avg, temp_max, humidity, rain, wind, solar, soil, gdd),
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}
