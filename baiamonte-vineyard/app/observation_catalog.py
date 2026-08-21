"""Controlled field-observation vocabulary and deterministic processing routes."""

from __future__ import annotations

from typing import Any


PHENOLOGY_STAGES = (
    ("dormant", "Dormant"),
    ("bud_swell", "Bud swell"),
    ("budbreak", "Budbreak"),
    ("shoot_growth", "Shoot growth"),
    ("flowering", "Flowering"),
    ("fruit_set", "Fruit set"),
    ("bunch_closure", "Bunch closure"),
    ("veraison", "Veraison"),
    ("ripening", "Ripening"),
    ("harvest_ready", "Harvest ready"),
    ("post_harvest", "Post-harvest"),
    ("leaf_fall", "Leaf fall"),
)


SCOUTING_ISSUES: tuple[dict[str, Any], ...] = (
    {"code": "healthy_normal", "label": "Healthy / normal growth", "pipelines": ("harvest_evidence_review",)},
    {"code": "fruit_maturity", "label": "Fruit maturity / ripening progress", "pipelines": ("harvest_evidence_review",)},
    {"code": "uneven_ripening", "label": "Uneven ripening / delayed maturity", "pipelines": ("harvest_evidence_review",)},
    {"code": "downy_mildew", "label": "Downy mildew / peronospora", "pipelines": ("treatment_prediction",)},
    {"code": "powdery_mildew", "label": "Powdery mildew / oidium", "pipelines": ("treatment_prediction",)},
    {"code": "botrytis_grey_mold", "label": "Botrytis / grey mold", "pipelines": ("treatment_prediction", "harvest_prediction")},
    {"code": "other_mold_rot", "label": "Other mold or rot", "pipelines": ("treatment_prediction", "harvest_prediction")},
    {"code": "hail", "label": "Hail damage", "pipelines": ("damage_assessment", "treatment_followup", "harvest_prediction"), "damage_type": "hail"},
    {"code": "hail_mold_rot", "label": "Hail damage with mold / rot symptoms", "pipelines": ("damage_assessment", "treatment_prediction", "harvest_prediction"), "damage_type": "hail"},
    {"code": "frost", "label": "Frost damage", "pipelines": ("damage_assessment", "harvest_prediction"), "damage_type": "frost"},
    {"code": "wind_storm", "label": "Wind or storm damage", "pipelines": ("damage_assessment", "harvest_prediction"), "damage_type": "wind_storm"},
    {"code": "sunburn_heat", "label": "Sunburn or heat damage", "pipelines": ("damage_assessment", "harvest_prediction"), "damage_type": "sunburn"},
    {"code": "wildlife_damage", "label": "Bird or animal damage", "pipelines": ("damage_assessment", "harvest_prediction"), "damage_type": "pest_animal"},
    {"code": "pest_insects", "label": "Pests or insects", "pipelines": ("agronomy_review",)},
    {"code": "water_stress_drought", "label": "Water stress or drought", "pipelines": ("stress_prediction", "harvest_prediction")},
    {"code": "nutrient_deficiency", "label": "Nutrient deficiency / chlorosis", "pipelines": ("agronomy_review", "harvest_prediction")},
    {"code": "weed_pressure", "label": "Weed pressure", "pipelines": ("agronomy_review",)},
    {"code": "other", "label": "Other / not listed", "pipelines": ("agronomy_review",), "requires_detail": True},
)


PIPELINE_LABELS = {
    "damage_assessment": "Damage assessment → AI percentage → approval → harvest adjustment",
    "treatment_prediction": "Treatment evidence + weather/phenology → product and timing prediction → Agronomist approval",
    "treatment_followup": "Hail wounds → 24–72 hour mold/rot photo review → treatment prediction only if symptoms support it",
    "stress_prediction": "Stress evidence → weather/irrigation screening → Agronomist review",
    "harvest_prediction": "Harvest evidence → yield and pick-date model refresh",
    "harvest_evidence_review": "Maturity report/photo → AI evidence check → harvest model refresh when supported",
    "agronomy_review": "Agronomy review queue → classification → approved follow-up",
}


def scouting_issue(code: Any) -> dict[str, Any]:
    normalized = str(code or "").strip().casefold().replace(" ", "_")
    for row in SCOUTING_ISSUES:
        if row["code"] == normalized:
            return dict(row)
    # Preserve compatibility with older integrations without allowing free text to
    # silently choose a safety-sensitive engine.
    return {"code": "other", "label": "Other / not listed", "pipelines": ("agronomy_review",), "requires_detail": True, "legacy_detail": str(code or "").strip()}


def phenology_stage(code: Any) -> tuple[str, str]:
    normalized = str(code or "").strip().casefold().replace(" ", "_")
    for stage_code, label in PHENOLOGY_STAGES:
        if stage_code == normalized:
            return stage_code, label
    raise ValueError("Choose a configured growth stage")


def reference_catalog() -> dict[str, Any]:
    issues = []
    for row in SCOUTING_ISSUES:
        item = dict(row)
        item["pipelines"] = [
            {"code": code, "label": PIPELINE_LABELS[code]} for code in row["pipelines"]
        ]
        issues.append(item)
    return {
        "scouting_issues": issues,
        "phenology_stages": [{"code": code, "label": label} for code, label in PHENOLOGY_STAGES],
        "pipeline_labels": PIPELINE_LABELS,
    }
