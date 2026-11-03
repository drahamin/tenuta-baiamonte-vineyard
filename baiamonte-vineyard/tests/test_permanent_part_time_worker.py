from app.domains import people_roles


def test_permanent_part_time_retains_hourly_model_and_part_time_scope(monkeypatch):
    profile = {"name": "Vincenzo (part-time)", "role": "Vineyard worker", "employment_type": "permanent_part_time"}
    monkeypatch.setattr(people_roles, "people_profiles", lambda: {"person.vincenzo_part_time": profile})
    assert people_roles.hourly_labor_terms(profile) == {
        "pay_model": "year_round_hourly", "payment_schedule": "Permanent part-time hourly reconciliation", "payroll_scope": "part_time",
    }
    assert people_roles.worker_profile("Vincenzo (part-time)") == {"role": "Vineyard worker", "payroll_scope": "part_time"}
    # A different worker sharing the first name must not inherit this identity.
    assert people_roles.worker_profile("Vincenzo (one-time olive harvest)")["role"] == "Seasonal labor"


def test_unspecified_hourly_workers_keep_existing_terms():
    assert people_roles.hourly_labor_terms({})["pay_model"] == "seasonal_hourly"
    assert people_roles.hourly_labor_terms({"employment_type": "contractor"})["payroll_scope"] == "contractor"
