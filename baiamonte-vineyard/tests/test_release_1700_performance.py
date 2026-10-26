from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_versioned_release_assets_are_immutable_but_unversioned_assets_revalidate():
    source = (ROOT / "app/cache_headers.py").read_text(encoding="utf-8")
    assert 'request.query_params.get("v")' in source
    assert 'public, max-age=31536000, immutable' in source
    assert 'no-cache, must-revalidate' in source


def test_today_boot_is_phased_and_heavy_workspaces_are_loaded_on_demand():
    source = (ROOT / "app/static/assets/performance.js").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/static/bootstrap.js").read_text(encoding="utf-8")
    initial = source[source.index("async function loadInitial"):source.index("let leafletLoadPromise")]
    deferred = source[source.index("async function loadDeferredData"):source.index("async function loadInitial")]
    assert "void loadInitial()" in bootstrap
    assert "api/v1/dashboard?year=" in initial
    initial_blocking = initial[initial.index("Promise.all"):initial.index("renderInitial()")]
    assert "api/v1/weather/current" not in initial_blocking
    assert "void loadCurrentWeather(request,year)" in initial
    assert "async function loadCurrentWeather" in source
    assert "api/v1/agronomy/dashboard" not in initial
    assert "api/v1/cellar/dashboard" not in initial
    assert "api/v1/agronomy/dashboard" not in deferred
    assert "api/v1/cellar/dashboard" not in deferred
    assert "api/v1/enology/process" not in deferred
    assert "api/v1/finance/dashboard" not in deferred
    assert "api/v1/system/status" in deferred
    assert "function workspaceFamily(view)" in source
    assert "loadWorkspaceView(view" in source
    assert "workspaceReady.has(key)" in source
    assert "view==='finance'" in source
    assert "operationsViews" in source
    assert "agronomyViews" in source
    assert "enologyViews" in source


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


def test_browser_read_concurrency_is_bounded_to_protect_interactive_latency():
    source = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "const maxConcurrentReads=4" in source
    assert "async function withReadSlot" in source
    assert "withReadSlot(operation)" in source


def test_workspace_families_do_not_cross_load_heavy_modules():
    source = (ROOT / "app/static/assets/performance.js").read_text(encoding="utf-8")
    finance = source.split("if(family==='finance')", 2)[2].split("if(family==='operations')", 1)[0]
    operations = source.split("if(family==='operations')", 2)[2].split("if(family==='agronomy')", 1)[0]
    assert "finance/dashboard" in finance
    assert "enology/process" not in finance
    assert "agronomy/dashboard" not in finance
    assert "issues?year=" in operations
    assert "processing-log" in operations
    assert "enology/process" not in operations
    assert "finance/dashboard" not in operations
    assert "workspaceReady.add(key)" in source
    assert "workspaceFamily(view)?loadWorkspaceView(view,true):loadAllWorkspace()" in source
