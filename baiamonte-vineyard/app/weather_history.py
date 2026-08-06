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
            try:
                weather_date = datetime.fromisoformat(row[1].strip()).date()
            except Exception:
                skipped += 1
                continue
            temp_avg, temp_min, temp_max = _number(row[2]), _number(row[3]), _number(row[4])
            humidity, rain, wind, solar, soil = _number(row[7]), _number(row[27]), _number(row[34]), _number(row[17]), _number(row[40])
            gdd = max(0.0, ((temp_min or temp_avg or 10) + (temp_max or temp_avg or 10)) / 2 - 10)
            cursor.execute(
                "INSERT INTO weather_daily (estate_id,station_id,weather_date,temp_min_c,temp_avg_c,temp_max_c,humidity_avg_pct,rain_mm,wind_max_kph,solar_mj_m2,soil_moisture_avg_pct,gdd_base10) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE temp_min_c=VALUES(temp_min_c),temp_avg_c=VALUES(temp_avg_c),temp_max_c=VALUES(temp_max_c),humidity_avg_pct=VALUES(humidity_avg_pct),rain_mm=VALUES(rain_mm),wind_max_kph=VALUES(wind_max_kph),solar_mj_m2=VALUES(solar_mj_m2),soil_moisture_avg_pct=VALUES(soil_moisture_avg_pct),gdd_base10=VALUES(gdd_base10)",
                (estate_id(), station_id, weather_date, temp_min, temp_avg, temp_max, humidity, rain, wind, solar, soil, gdd),
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}
