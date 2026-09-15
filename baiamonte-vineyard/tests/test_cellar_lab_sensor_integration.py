from __future__ import annotations

from app.domains import cellar_routes, laboratory


def _row(sample_id: str, *, wine_lot_id=None, linked_wine_lot_ids=None, sample_code="", sample_name="Nerello", needs_review=0, analyte="ph", value=3.4):
    return {
        "sample_id": sample_id,
        "wine_lot_id": wine_lot_id,
        "linked_wine_lot_ids": linked_wine_lot_ids,
        "sample_code": sample_code,
        "sample_name": sample_name,
        "source_sample_name": sample_name,
        "canonical_sample_name": None,
        "sample_type": "wine",
        "sampled_at": "2026-08-28T12:00:00",
        "lab_date": "2026-08-28",
        "laboratory": "CI.MA.LAB",
        "source_document": f"/api/v1/labs/reports/{sample_id}",
        "needs_review": needs_review,
        "review_notes": None,
        "vintage_year": 2026,
        "vintage_assignment_confidence": "confirmed",
        "review_status": "closed" if not needs_review else "reviewing",
        "interpretation": "Measured wine result",
        "decision_action": "Continue monitoring",
        "approved_by": "Enologist" if not needs_review else None,
        "approved_at": "2026-08-28T13:00:00" if not needs_review else None,
        "result_id": f"{sample_id}-{analyte}",
        "analyte_code": analyte,
        "analyte_name": analyte,
        "numeric_value": value,
        "text_value": None,
        "unit": "" if analyte == "ph" else "g/L",
        "flag": "normal",
    }


def test_exact_wine_lot_lab_report_is_grouped_and_authoritative(monkeypatch):
    rows = [
        _row("sample-1", wine_lot_id="lot-1", analyte="ph", value=3.42),
        _row("sample-1", wine_lot_id="lot-1", analyte="malic_acid", value=1.1),
        _row("other", wine_lot_id="lot-2", sample_name="Grenache"),
    ]
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [{
        "id": "tank-1",
        "code": "T-01",
        "lot_code": "NER-26-01",
        "wine_lot_id": "lot-1",
        "variety_summary": "Nerello Mascalese",
        "started_at": "2026-08-20",
    }]

    laboratory.cellar_laboratory_evidence(tanks, 2026)

    evidence = tanks[0]["laboratory_evidence"]
    assert evidence["sample_count"] == 1
    assert evidence["confirmed_count"] == 1
    assert evidence["authoritative_count"] == 1
    assert evidence["samples"][0]["match_method"] == "wine_lot"
    assert evidence["samples"][0]["authoritative_for_tank"] is True
    assert {result["analyte_code"] for result in evidence["samples"][0]["results"]} == {"ph", "malic_acid"}


def test_unreviewed_exact_report_is_visible_but_not_authoritative(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [
        _row("sample-1", sample_code="NER-26-01", needs_review=1),
    ])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [{"id": "tank-1", "code": "T-01", "lot_code": "NER-26-01", "variety_summary": "Nerello"}]

    laboratory.cellar_laboratory_evidence(tanks, 2026)

    evidence = tanks[0]["laboratory_evidence"]
    assert evidence["confirmed_count"] == 1
    assert evidence["authoritative_count"] == 0
    assert evidence["samples"][0]["authoritative_for_tank"] is False


def test_name_only_report_is_ambiguous_when_two_tanks_share_the_wine(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [_row("sample-1", sample_name="Narello Macalase")])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [
        {"id": "tank-1", "code": "T-01", "lot_code": "NER-A", "variety_summary": "Nerello Mascalese", "started_at": "2026-08-20"},
        {"id": "tank-2", "code": "T-02", "lot_code": "NER-B", "variety_summary": "Nerello", "started_at": "2026-08-21"},
    ]

    laboratory.cellar_laboratory_evidence(tanks, 2026)

    for tank in tanks:
        evidence = tank["laboratory_evidence"]
        assert evidence["ambiguous_count"] == 1
        assert evidence["probable_count"] == 0
        assert evidence["authoritative_count"] == 0
        assert evidence["samples"][0]["match_confidence"] == "ambiguous"
        assert "more than one tank" in evidence["samples"][0]["match_evidence"]


def test_unique_normalized_wine_match_remains_probable(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [_row("sample-1", sample_name="Narello Macalase")])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [{"id": "tank-1", "code": "T-01", "lot_code": "NER-A", "variety_summary": "Nerello", "started_at": "2026-08-20"}]

    laboratory.cellar_laboratory_evidence(tanks, 2026)

    evidence = tanks[0]["laboratory_evidence"]
    assert evidence["probable_count"] == 1
    assert evidence["ambiguous_count"] == 0
    assert evidence["authoritative_count"] == 0


def test_public_label_mode_rejects_name_only_matches(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [_row("sample-1", sample_name="Narello Macalase")])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [{"id": "tank-1", "code": "T-01", "lot_code": "NER-A", "variety_summary": "Nerello", "started_at": "2026-08-20"}]

    laboratory.cellar_laboratory_evidence(tanks, 2026, include_name_matches=False)

    evidence = tanks[0]["laboratory_evidence"]
    assert evidence["sample_count"] == 0
    assert evidence["authoritative_count"] == 0


def test_public_label_accepts_exact_wine_lot_code(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [
        _row("sample-1", sample_code="NER-26-01", sample_name="Unhelpful legacy name"),
    ])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [{"id": "tank-1", "code": "T-01", "wine_lot_code": "NER-26-01", "variety_summary": "Nerello"}]

    laboratory.cellar_laboratory_evidence(tanks, 2026, include_name_matches=False)

    evidence = tanks[0]["laboratory_evidence"]
    assert evidence["sample_count"] == 1
    assert evidence["confirmed_count"] == 1
    assert evidence["samples"][0]["match_method"] == "lot_or_tank_code"


def test_junction_linked_lab_report_is_authoritative_for_each_linked_lot(monkeypatch):
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [
        _row("sample-1", linked_wine_lot_ids="lot-primary,lot-final", sample_name="Grecanico must", analyte="yan", value=124),
    ])
    monkeypatch.setattr(laboratory, "estate_id", lambda: "estate-1")
    tanks = [
        {"id": "tank-3", "code": "T-03", "wine_lot_id": "lot-primary", "variety_summary": "Grecanico"},
        {"id": "tank-44", "code": "T-44", "wine_lot_id": "lot-final", "variety_summary": "Grecanico"},
    ]

    laboratory.cellar_laboratory_evidence(tanks, 2026)

    for tank in tanks:
        evidence = tank["laboratory_evidence"]
        assert evidence["authoritative_count"] == 1
        assert evidence["samples"][0]["match_method"] == "wine_lot"
        assert evidence["samples"][0]["authoritative_for_tank"] is True


def test_tank_calculated_metrics_include_babo_progress_and_linked_lab_values():
    tank = {
        "fermentation_process": [
            {"observed_at": "2026-09-12T09:00:00", "babo": 16},
            {"observed_at": "2026-09-13T12:35:00", "babo": 11.8},
            {"observed_at": "2026-09-15T18:00:00", "babo": 2.2},
        ],
        "laboratory_evidence": {
            "samples": [{
                "authoritative_for_tank": True,
                "results": [
                    {"analyte_code": "potential_alcohol", "numeric_value": 11.82},
                    {"analyte_code": "yan", "numeric_value": 124},
                    {"analyte_code": "ntu", "numeric_value": 90},
                ],
            }],
        },
    }

    metrics = cellar_routes._tank_calculated_metrics(tank)

    assert metrics["babo_start"] == 16
    assert metrics["babo_latest"] == 2.2
    assert metrics["babo_progress_pct"] == 86.2
    assert metrics["potential_alcohol_pct"] == 11.82
    assert metrics["yan_mg_l"] == 124
    assert metrics["turbidity_ntu"] == 90
