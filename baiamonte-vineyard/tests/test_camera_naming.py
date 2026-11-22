from pathlib import Path

from app.domains.camera_naming import canonical_camera_name


ROOT = Path(__file__).resolve().parents[1]


def test_operational_camera_names_override_legacy_names():
    assert canonical_camera_name("camera.vineyard_north", "Vineyard North") == "Main Parking"
    assert canonical_camera_name("camera.t8171t1025291b5f", "T8171T1025291B5F") == "Rear Gate 360"
    assert canonical_camera_name("camera.top_vineyard_360", "Top Vineyard 360") == "Rear Entrance Path 360"
    assert canonical_camera_name("camera.cistern_360", "Water Camera") == "Cistern 360"
    assert canonical_camera_name("camera.topvineyard", "Top Vineyard") == "Backyard"
    assert canonical_camera_name("camera.rear_gate_360", "Rear Gate 360") == "Back Driveway Mid"
    assert canonical_camera_name("camera.fox_ally", "Fox Ally") == "Fox Alley"
    assert canonical_camera_name("camera.indoor_cam", "Garage / Fox Den") == "Fox Den"


def test_unknown_camera_keeps_clean_home_assistant_name():
    assert canonical_camera_name("camera.garage", " Garage  /  Fox Den ") == "Garage / Fox Den"
    assert canonical_camera_name("camera.unlisted_room") == "unlisted room"


def test_vineyard_visual_fallback_uses_the_current_vineyard_north_entity():
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    capture = source.split("def _capture_vineyard_visual_frame", 1)[1].split("\ndef ", 1)[0]
    assert 'home_assistant_camera_snapshot("camera.vineyard_north_2")' in capture
    assert '"/services/eufy_security/capture_snapshot"' in capture
    assert '"home_assistant_forced_snapshot"' in capture


def test_front_gate_locations_follow_current_device_names():
    assert canonical_camera_name("camera.front_gate", "Front Yard") == "Front Yard"
    assert canonical_camera_name("camera.front_yard", "Front Gate Inside") == "Inside Front Gate"


def test_confirmed_second_c31_has_a_separate_camera_card():
    import yaml
    assert canonical_camera_name("camera.t817lt0026120afa") == "Additional Camera"
    document = yaml.safe_load((ROOT / "dashboards/vineyard-overview.yaml").read_text())
    page = next(view for view in document["views"] if view.get("path") == "new-cameras")
    cards = [card for section in page["sections"] for card in section.get("cards", [])]
    assert any(card.get("name") == "Additional Camera" and card.get("entity") == "image.t817lt0026120afa_event_image" for card in cards)
    assert any(card.get("name") == "Garage" for card in cards)


def test_camera_and_security_cards_bind_each_location_consistently():
    import yaml
    expected = {'Inside Front Gate': 'front_yard', 'Front Yard': 'front_gate',
                'Back Driveway Mid': 'rear_gate_360', 'Backyard': 'topvineyard'}
    document = yaml.safe_load((ROOT / 'dashboards/vineyard-overview.yaml').read_text())
    def walk(value):
        if isinstance(value, dict):
            label = value.get('name') or value.get('title')
            entity = value.get('entity') or value.get('camera_image')
            if isinstance(label, str) and label in expected and isinstance(entity, str) and entity.startswith(('camera.', 'image.')):
                wanted = 'image.' + expected[label] + '_event_image' if entity.startswith('image.') else 'camera.' + expected[label]
                assert entity == wanted, (label, entity)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(document)


def test_exact_operational_name_requests_do_not_follow_misleading_legacy_ids(monkeypatch):
    from app import intelligence
    cameras = [{"entity_id": "camera.front_gate", "name": "Front Yard"},
               {"entity_id": "camera.front_yard", "name": "Inside Front Gate"}]
    monkeypatch.setattr(intelligence, "home_assistant_manager_cameras", lambda: cameras)
    assert intelligence.resolve_home_assistant_camera_request("SEND Front Yard PHOTO")["camera"]["entity_id"] == "camera.front_gate"
    assert intelligence.resolve_home_assistant_camera_request("SEND Inside Front Gate PHOTO")["camera"]["entity_id"] == "camera.front_yard"
    assert intelligence.resolve_home_assistant_camera_request("send camera.front_yard photo")["camera"]["entity_id"] == "camera.front_yard"


def test_a_known_but_unexposed_location_does_not_select_a_neighbor(monkeypatch):
    from app import intelligence
    monkeypatch.setattr(intelligence, "home_assistant_manager_cameras", lambda: [
        {"entity_id": "camera.front_yard", "name": "Inside Front Gate"}])
    assert intelligence.resolve_home_assistant_camera_request("SEND Front Yard PHOTO")["action"] == "list"
