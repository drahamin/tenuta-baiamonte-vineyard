"""Opt-in synthetic concurrency test. Never points at a remote database."""
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch

import pymysql
import pytest

from app.mcp_server import record_sebastiano_tank_reading


@pytest.mark.skipif(not os.getenv("BAIAMONTE_TEST_DB_PORT"), reason="isolated MariaDB not configured")
def test_two_writers_serialize_on_real_innodb():
    port = int(os.environ["BAIAMONTE_TEST_DB_PORT"])
    def connect():
        return pymysql.connect(host="127.0.0.1", port=port, user="root", password="", database="identity_test", cursorclass=pymysql.cursors.DictCursor)

    with connect() as c:
        with c.cursor() as cur:
            cur.execute("CREATE TABLE estates (id CHAR(36) PRIMARY KEY) ENGINE=InnoDB")
            cur.execute("CREATE TABLE seasons (id CHAR(36) PRIMARY KEY, vintage_year INT) ENGINE=InnoDB")
            cur.execute("CREATE TABLE wine_lots (id CHAR(36) PRIMARY KEY, estate_id CHAR(36), season_id CHAR(36), code VARCHAR(40), stage VARCHAR(40), variety_summary VARCHAR(40), lot_status VARCHAR(20), current_container_id CHAR(36)) ENGINE=InnoDB")
            cur.execute("CREATE TABLE cellar_containers (id CHAR(36) PRIMARY KEY, estate_id CHAR(36), code VARCHAR(40), name VARCHAR(40), status VARCHAR(20), active BOOLEAN) ENGINE=InnoDB")
            cur.execute("CREATE TABLE fermentation_observations (id CHAR(36) PRIMARY KEY, estate_id CHAR(36), wine_lot_id CHAR(36), source_observation_id VARCHAR(120), observed_at DATETIME(6), vessel_name VARCHAR(160), stage VARCHAR(80), temp_c DECIMAL(7,3), babo DECIMAL(7,3), sensory_observation TEXT, owner_text VARCHAR(160), status VARCHAR(80), UNIQUE KEY uq_fermentation_source (estate_id,source_observation_id)) ENGINE=InnoDB")
            cur.execute("CREATE TABLE integration_events (estate_id CHAR(36), integration_name VARCHAR(80), direction VARCHAR(20), event_type VARCHAR(80), external_id VARCHAR(500), status VARCHAR(40), payload TEXT) ENGINE=InnoDB")
            cur.execute("INSERT INTO estates VALUES ('estate')")
            cur.execute("INSERT INTO seasons VALUES ('season',2026)")
            cur.execute("INSERT INTO cellar_containers VALUES ('tank','estate','T-39','Tank 39','in_use',1)")
            cur.execute("INSERT INTO wine_lots VALUES ('lot','estate','season','GRN-2026-02','fermentation','Grenache','active','tank')")
        c.commit()

    @contextmanager
    def transaction():
        c = connect()
        try:
            with c.cursor() as cur:
                yield c, cur
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    args = dict(platform_message_id="SYNTHETIC-TEST-ONLY", observed_at="2026-11-01T12:00:00+01:00", source_text="9 Babo", babo=9, confirmation="RECORD SEBASTIANO TANK READING", verified_lid="123@lid", mapping_provenance="synthetic test")
    with patch("app.mcp_server.require_write_confirmation"), patch("app.mcp_server.estate_id", return_value="estate"), patch("app.mcp_server.transaction", side_effect=transaction), patch("app.mcp_server.audit"), patch("app.mcp_server.fetch_one", return_value={"reading_id":"synthetic"}):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: record_sebastiano_tank_reading(**args), range(2)))
    assert all(r["review_required"] and not r["recorded"] for r in results)
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM fermentation_observations")
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT COUNT(*) n FROM integration_events")
            assert cur.fetchone()["n"] == 0
