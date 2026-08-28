from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_versioned_release_assets_are_immutable_but_unversioned_assets_revalidate():
    source = (ROOT / "app/cache_headers.py").read_text(encoding="utf-8")
    assert 'request.query_params.get("v")' in source
    assert 'public, max-age=31536000, immutable' in source
    assert 'no-cache, must-revalidate' in source


def test_today_boot_is_phased_and_heavy_workspaces_are_deferred():
    source = (ROOT / "app/static/assets/performance.js").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/static/bootstrap.js").read_text(encoding="utf-8")
    initial = source[source.index("async function loadInitial"):source.index("let leafletLoadPromise")]
    deferred = source[source.index("async function loadDeferredData"):source.index("async function loadInitial")]
    assert "void loadInitial()" in bootstrap
    assert "api/v1/dashboard?year=" in initial
    assert "api/v1/weather/current" in initial
    assert "api/v1/agronomy/dashboard" not in initial
    assert "api/v1/cellar/dashboard" not in initial
    assert "api/v1/agronomy/dashboard" in deferred
    assert "api/v1/cellar/dashboard" in deferred


def test_leaflet_is_not_a_blocking_document_asset():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    source = (ROOT / "app/static/assets/performance.js").read_text(encoding="utf-8")
    assert "unpkg.com/leaflet" not in html
    assert "function ensureLeaflet()" in source
    assert "cdn.jsdelivr.net/npm/leaflet" in source


def test_public_feed_checkpoint_uses_database_local_time_consistently():
    source = (ROOT / "app/publisher.py").read_text(encoding="utf-8")
    assert "UTC_TIMESTAMP()" not in source
    assert source.count("NOW()") >= 6
