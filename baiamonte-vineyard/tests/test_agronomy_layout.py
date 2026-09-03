from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_enology_uses_task_first_collapsible_cellar_layout() -> None:
    html = (ROOT / "app/static/index.html").read_text()
    css = (ROOT / "app/static/app.css").read_text()
    js = (ROOT / "app/static/assets/cellar.js").read_text()

    assert 'class="agronomy-quick-actions"' in html
    assert 'id="agronomyLegalLabels"' in html
    assert 'id="agronomyTankRegister"><summary>' in html
    assert 'id="agronomyWineLegalLabel"' in html
    assert 'class="agronomy-subpanel" id="agronomyWineLegalLabel"' in html
    assert 'id="agronomyBlendPlanningPanel"><summary>' in html
    assert 'id="agronomyLabelTablets"' in html
    assert 'id="agronomyVesselReading" open' not in html
    assert 'id="agronomyHarvestTrace"><summary>' in html
    assert 'id="cellarProcessChecks"><summary>' in html
    assert ".agronomy-subpanel>summary" in css
    assert "[data-agronomy-target]" in js
    assert "wine.open=true" in js


def test_agronomy_and_enology_are_separate_workspaces() -> None:
    html = (ROOT / "app/static/index.html").read_text()
    enology = html.split('<section class="view" id="view-cellar">', 1)[1].split(
        '<section class="view" id="view-agronomy"', 1
    )[0]
    agronomy = html.split('<section class="view" id="view-agronomy"', 1)[1].split(
        '<section class="view" id="view-projections">', 1
    )[0]

    assert 'data-nav-mode="agronomy">Agronomy</button>' in html
    assert 'data-nav-mode="enology">Enology</button>' in html
    assert 'data-view="cellar" data-enology-panel="overview" data-icon="◫">Cellar</button>' in html
    assert 'data-view="cellar" data-enology-panel="winemaking" data-icon="⚗">Winemaking</button>' in html
    assert 'data-enology-panel-content="winemaking"' in enology
    assert "Process stages &amp; evidence gates" in enology
    assert "Enology &amp; cellar operations" in enology
    assert "Tank records &amp; cellar controls" in enology
    assert 'id="agronomyTankRegister"' in enology
    assert 'id="agronomyLegalLabels"' in enology
    assert 'id="agronomyVesselReading"' in enology
    assert 'id="agronomyHarvestTrace"' in enology
    assert "Agronomy &amp; cellar control" not in html
    assert "Field scouting" in agronomy
    assert "Phenology" in agronomy
    assert "Fruit maturity" in agronomy
    assert 'data-jump="treatments"' in agronomy
    assert 'id="agronomyTankRegister"' not in agronomy
    assert 'id="agronomyTreatmentReview"' not in html
