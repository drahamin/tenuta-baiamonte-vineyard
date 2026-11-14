import hashlib
import tempfile
import unittest
from pathlib import Path

from app.domains.cistern_reference import accepted_fraction, reference_image


class CisternReferenceTests(unittest.TestCase):
    def test_full_water_can_match_owner_frame_with_floor_submerged(self):
        reference = {'id': 'full-today', 'level_percent': 100}
        analysis = dict(usable=True, visible_waterline=True, waterline_height_fraction=1,
                        confidence=.9, calibration_landmarks_visible=False,
                        measurement_method='owner_reference_match', reference_id='full-today',
                        camera_geometry_matches_reference=True, same_surface_height_as_reference=True)
        self.assertEqual(accepted_fraction(analysis, reference), 1)
        for change in ({'reference_id': 'wrong'}, {'camera_geometry_matches_reference': False},
                       {'same_surface_height_as_reference': False}, {'confidence': .7},
                       {'waterline_height_fraction': .7}, {'visible_waterline': False}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                accepted_fraction({**analysis, **change}, reference)
        with self.assertRaises(ValueError):
            accepted_fraction(analysis, None)

    def test_other_levels_require_both_physical_height_anchors(self):
        analysis = dict(usable=True, visible_waterline=True, waterline_height_fraction=.35,
                        confidence=.85, calibration_landmarks_visible=True)
        self.assertEqual(accepted_fraction(analysis, None), .35)
        for change in ({'calibration_landmarks_visible': False}, {'confidence': 'nan'},
                       {'waterline_height_fraction': 'nan'}, {'confidence': 2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                accepted_fraction({**analysis, **change}, None)

    def test_exact_reviewed_frame_is_retained_before_snapshot_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / 'latest'
            snapshot.write_bytes(b'owner frame')
            row = dict(image_sha256=hashlib.sha256(b'owner frame').hexdigest(),
                       metadata={'owner_assisted': True, 'calibration_reference': 'fixed-view'},
                       source='owner_assisted_camera_review', camera_entity_id='camera.cisterna')
            self.assertEqual(reference_image(snapshot, row, 'camera.cisterna', 'fixed-view'), b'owner frame')
            snapshot.write_bytes(b'new frame')
            self.assertEqual(reference_image(snapshot, row, 'camera.cisterna', 'fixed-view'), b'owner frame')
            for change in ({'source': 'camera_ai'}, {'camera_entity_id': 'camera.other'},
                           {'image_sha256': '../untrusted'}, {'image_sha256': 'a'*64}):
                self.assertIsNone(reference_image(snapshot, {**row, **change}, 'camera.cisterna', 'fixed-view'))


class CisternPipelineTests(unittest.TestCase):
    def test_live_request_attaches_verified_owner_frame_before_current_frame(self):
        import base64
        import json
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import patch
        from app import intelligence as pipeline
        settings = SimpleNamespace(cistern_level_ai_enabled=True, openai_api_key='test-key',
                                   cistern_camera_entity='camera.cisterna', cistern_level_initial_percent=20,
                                   openai_model='test-model')
        reference = dict(id='owner-full', level_percent=100, image_sha256='a'*64)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            snapshot = Path(directory) / 'latest'
            dashboard = Path(directory) / 'dashboard'
            # Map only the hard-coded HA dashboard cache to our disposable directory.
            real_path = Path
            stack.enter_context(patch.object(pipeline, 'Path', side_effect=lambda value: dashboard if str(value).startswith('/homeassistant/') else real_path(value)))
            mocks = {}
            values = {'ai_response_options': {}, 'get_settings': settings, 'latest_cistern_level': {'level_percent': 100},
                      'prepare_cistern_shadow_prediction': None, 'home_assistant_token': 'test-token',
                      'fetch_one': reference, 'reference_image': b'owner-full-image', '_ha_get': [],
                      '_cistern_camera_light': (None, False),
                      '_capture_cistern_image': (b'current-frame', 'image/jpeg', False, 'test'),
                      '_response_text': json.dumps({'usable': False, 'visible_waterline': False})}
            for name in set(values) | {'_publish_cistern_level', '_stop_cistern_camera_stream',
                                      '_restore_cistern_camera_light', 'resolve_condition_alert',
                                      'upsert_condition_alert', 'record_ai_usage', '_openai_json_request'}:
                mocks[name] = stack.enter_context(patch.object(pipeline, name, return_value=values.get(name)))
            stack.enter_context(patch.object(pipeline, 'CISTERN_SNAPSHOT_PATH', snapshot))
            result = pipeline.refresh_cistern_level()
            self.assertFalse(result['updated'])
            request = mocks['_openai_json_request'].call_args.args[0]
            content = json.loads(request.data)['input'][0]['content']
            images = [part['image_url'].split(',', 1)[1] for part in content if part['type'] == 'input_image']
            self.assertEqual([base64.b64decode(value) for value in images], [b'owner-full-image', b'current-frame'])
            self.assertEqual(snapshot.read_bytes(), b'current-frame')
            self.assertEqual(mocks['upsert_condition_alert'].call_args.args[4], 'cistern-waterline-unverified')
