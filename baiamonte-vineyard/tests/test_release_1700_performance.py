from pathlib import Path

from app.domains.enology_process import _enology_process_scope


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


def test_enology_workspace_defers_large_recipe_catalog_and_history_payloads():
    performance = (ROOT / "app/static/assets/performance.js").read_text(encoding="utf-8")
    renderer = (ROOT / "app/static/assets/enology-process.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/domains/enology_process.py").read_text(encoding="utf-8")
    assert "enology/process?year=${year}&scope=summary" in performance
    assert "scope=lot&lot_id=${encodeURIComponent(lotId)}" in renderer
    assert "scope=catalog" in renderer
    assert "scope=history" in renderer
    assert "def _enology_process_scope" in backend
    assert 'if scope == "full"' in backend
    assert 'if scope == "summary"' not in backend  # summary is the validated fallback projection
    assert '"deferred_scopes"' in backend


def test_enology_summary_keeps_status_but_defers_selected_lot_recipe_data():
    response = {
        "year": 2026,
        "lots": [{
            "id": "lot-1", "code": "NM-2026-01", "checks": [{"state": "ready"}],
            "product_suggestions": [{"id": "product-1", "description": "large" * 100}],
            "additive_prediction_pipeline": {
                "blocked_count": 2, "due_count": 1,
                "decisions": [{"id": "decision-1", "description": "large" * 100}],
                "streamlined_recipe": {"current_actions": [{"id": "action-1"}]},
            },
        }],
        "product_catalog": [{"id": "product-1"}],
        "product_protocols": [{"id": "protocol-1"}],
        "product_catalog_summary": {"products": 1},
        "chemistry_vintage_overlay": [{"value": 3.4}],
        "fermentation_vintage_overlay": [{"density_sg": 0.995}],
    }
    summary = _enology_process_scope(response, "summary", None)
    assert summary["lots"][0]["checks"] == [{"state": "ready"}]
    assert summary["lots"][0]["additive_prediction_pipeline"] == {"blocked_count": 2, "due_count": 1}
    assert summary["lots"][0]["product_suggestions"] == []
    assert summary["product_catalog"] == []
    assert summary["chemistry_vintage_overlay"] == []
    assert _enology_process_scope(response, "lot", "lot-1")["lot"] is response["lots"][0]
    assert _enology_process_scope(response, "catalog", None)["product_catalog"] == [{"id": "product-1"}]
    assert _enology_process_scope(response, "history", None)["chemistry_vintage_overlay"] == [{"value": 3.4}]
