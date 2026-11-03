from app.domains import security


def test_gate_verifies_even_confident_plate_without_registry_context(monkeypatch):
    seen = []
    monkeypatch.setattr(security, "_plate_crop", lambda image, box: b"original-pixel-crop")
    def read(crop, camera_name):
        seen.append((crop, camera_name))
        return {"license_plate": "DP971EV", "plate_pattern": "DP971EV", "plate_confidence": .95}
    monkeypatch.setattr(security, "_read_plate_crop", read)
    rows = [{"license_plate": "DF706MZ", "plate_confidence": .9} for _ in range(3)]
    result = security._enrich_plate_reads(b"source", rows, "Front Gate Doorbell", verify_plate=True)
    assert seen == [(b"original-pixel-crop", "Front Gate Doorbell")] * 2
    assert [row["license_plate"] for row in result] == ["DP971EV", "DP971EV", "DF706MZ"]


def test_non_gate_clear_plate_keeps_existing_bounded_path(monkeypatch):
    monkeypatch.setattr(security, "_read_plate_crop", lambda *_: (_ for _ in ()).throw(AssertionError("unneeded read")))
    rows = [{"license_plate": "DP971EV", "plate_confidence": .9}]
    assert security._enrich_plate_reads(b"source", rows, "Main Parking") == rows


def test_exact_plate_corrects_silver_car_appearance_match():
    staff = [{"person_entity": "person.vincenzo", "vehicles": [{"plate": "DP971EV"}]},
             {"person_entity": "person.giancarlo", "vehicles": [{"plate": "DF706MZ"}]}]
    known = [{"id": "opel", "person_entity": "person.vincenzo", "license_plate": "DP971EV"}]
    row = {"license_plate": "DP971EV", "plate_confidence": .95,
           "staff_person_entity": "person.giancarlo", "known_vehicle_id": "golf"}
    security._resolve_exact_plate_identity(row, staff, known)
    assert row["staff_person_entity"] == "person.vincenzo"
    assert row["known_vehicle_id"] == "opel"


def test_shared_plate_configuration_never_selects_a_person():
    staff = [{"person_entity": name, "vehicles": [{"plate": "DP971EV"}]} for name in ("person.a", "person.b")]
    row = {"license_plate": "DP971EV", "plate_confidence": .95, "staff_person_entity": "person.a"}
    security._resolve_exact_plate_identity(row, staff, [])
    assert row["staff_person_entity"] is None
    assert row["known_vehicle_id"] is None
