import pytest

from app.cellar_identity import canonical_container_code, canonical_variety, cellar_identity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3", "T-03"), ("Tank 3", "T-03"), ("serbatoio #39", "T-39"), ("t_044", "T-44")],
)
def test_tank_codes_are_canonical(raw, expected):
    assert canonical_container_code(raw, "tank") == expected


def test_non_tank_physical_codes_stay_distinct():
    assert canonical_container_code("dj l54", "demijohn") == "DJ-L54"


def test_tank_codes_reject_wine_names():
    with pytest.raises(ValueError, match="T-01"):
        canonical_container_code("2026 Grenache", "tank")


@pytest.mark.parametrize("raw", ["Alicante", "Alicante Bouschet", "Grenache", "Grenache Noir"])
def test_grenache_alicante_aliases_share_one_display_name(raw):
    assert canonical_variety(raw) == "Grenache / Alicante"


def test_identity_keeps_physical_asset_and_current_wine_separate():
    result = cellar_identity({
        "code": "Tank 39",
        "name": "Raiti 1,000 L",
        "container_type": "tank",
        "vintage_year": 2026,
        "variety_summary": "Alicante",
        "lot_code": "grn-2026-02",
        "stage": "aging",
        "status": "in_use",
    })
    assert result["identity_label"] == "2026 · T-39 · Grenache / Alicante · GRN-2026-02"
    assert result["asset_name"] == "Tank 39 · Raiti 1,000 L"
    assert result["identity_stage"] == "aging"


def test_empty_tank_does_not_claim_a_vintage():
    result = cellar_identity({"code": "T-03", "name": "Tank 3 · Grecanico 2026", "container_type": "tank", "status": "empty", "variety_summary": "Alicante"})
    assert result["identity_label"] == "T-03"
    assert result["identity_vintage"] is None
    assert result["identity_stage"] == "Empty"
    assert result["canonical_variety"] is None
    assert result["asset_name"] == "Tank 3"


def test_legacy_content_based_codes_are_marked_for_review():
    result = cellar_identity({
        "code": "CT-GRC-P-2026",
        "name": "Grecanico primary",
        "container_type": "other",
        "vintage_year": 2026,
        "variety_summary": "Grecanico",
        "lot_code": "GRC-2026-01-P",
        "status": "in_use",
    })
    assert result["identity_needs_review"] is True
    assert "Physical code contains wine or vintage information" in result["identity_warnings"]
