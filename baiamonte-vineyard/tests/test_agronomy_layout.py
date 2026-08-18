from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agronomy_uses_task_first_collapsible_layout() -> None:
    html = (ROOT / "app/static/index.html").read_text()
    css = (ROOT / "app/static/app.css").read_text()
    js = (ROOT / "app/static/assets/cellar.js").read_text()

    assert 'class="agronomy-quick-actions"' in html
    assert 'id="agronomyLegalLabels"' in html
    assert 'id="agronomyTankRegister"><summary>' in html
    assert 'id="agronomyWineLegalLabel"' in html
    assert 'class="agronomy-subpanel" id="agronomyWineLegalLabel"' in html
    assert 'id="agronomyBlendPlanningPanel"><summary>' in html
    assert 'id="agronomyVesselReading" open' in html
    assert ".agronomy-subpanel>summary" in css
    assert "[data-agronomy-target]" in js
    assert "wine.open=true" in js
