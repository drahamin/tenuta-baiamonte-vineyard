import json
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import pytest
from app import intelligence as pipeline


def item(external, parent=None, source='gmail'):
    return dict(id=str(uuid4()), source=source, external_id=external,
                source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': parent}) if parent else '{}',
                sender_address='lab@example.test', stored_path=None)


def test_recovery_uses_verified_parent_and_bounded_source_scoped_lookup():
    parent = item('gmail-message:body')
    report = item('gmail-message:manual-report-abc', parent['id'])
    with patch.object(pipeline, 'estate_id', return_value='estate-1'), patch.object(pipeline, 'fetch_one', return_value=parent) as select:
        assert pipeline._intake_review_alert_source_key(report) == pipeline.source_message_key(parent)
        sql, params = select.call_args.args
        assert 'id=%s AND estate_id=%s AND source=%s' in sql
        assert params == (parent['id'], 'estate-1', 'gmail')
    with patch.object(pipeline, 'estate_id', return_value='estate-1'), patch.object(pipeline, 'fetch_one', return_value=None):
        assert pipeline._intake_review_alert_source_key(report) == report['external_id']


def test_nested_recoveries_resolve_parent_and_cycles_fail_closed():
    parent = item('gmail-message:attachment-0')
    first = item('first-recovery', parent['id'])
    second = item('second-recovery', first['id'])
    with patch.object(pipeline, 'estate_id', return_value='estate-1'), patch.object(pipeline, 'fetch_one', side_effect=[first, parent]):
        assert pipeline._intake_review_alert_source_key(second) == 'gmail-message'
    first['source_metadata'] = json.dumps({'attachment_recovery': True, 'manually_attached_to': second['id']})
    with patch.object(pipeline, 'estate_id', return_value='estate-1'), patch.object(pipeline, 'fetch_one', return_value=first):
        assert pipeline._intake_review_alert_source_key(second) == 'second-recovery'


@pytest.mark.parametrize('source,external', [('gmail', 'gmail-message:body'), ('whatsapp', 'system-wa:1:message:body')])
def test_parent_and_recovered_report_create_one_alert_and_one_notification(source, external):
    parent = item(external, source=source)
    report = item('recovered:manual-report-abc', parent['id'], source)
    rows = {row['id']: row for row in (parent, report)}
    alerts = set()
    class Cursor:
        found = None
        def execute(self, sql, params):
            if sql.startswith('SELECT id FROM alerts'):
                self.found = {'id': 'existing-alert'} if params[1] in alerts else None
            elif sql.startswith('INSERT INTO alerts'):
                alerts.add(params[6])
            return 1
        def fetchone(self):
            return self.found
    @contextmanager
    def transaction():
        yield None, Cursor()
    def select(sql, params):
        if sql.startswith('SELECT * FROM intake_items'):
            return rows[params[0]]
        assert 'id=%s AND estate_id=%s AND source=%s' in sql
        row = rows.get(params[0])
        return row if row and row['source'] == params[2] else None
    parsed = {'classification': 'lab_report', 'summary': 'Report needs review', 'uncertainties': ['Review required']}
    with ExitStack() as stack:
        for name, value in {'get_settings': SimpleNamespace(openai_api_key='test-key', openai_model='test-model'),
                            'estate_id': 'estate-1', 'fetch_all': [], 'ai_response_options': {},
                            '_openai_json_request': {'output_text': json.dumps(parsed)}, 'record_ai_usage': None,
                            '_trusted_gmail_senders': {'lab@example.test'},
                            'alert_preference': {'enabled': True, 'min_severity': 'warning'}}.items():
            stack.enter_context(patch.object(pipeline, name, return_value=value))
        stack.enter_context(patch.object(pipeline, 'fetch_one', side_effect=select))
        stack.enter_context(patch.object(pipeline, 'transaction', transaction))
        notify = stack.enter_context(patch.object(pipeline, 'send_alert_notifications'))
        pipeline.analyze_intake(parent['id'])
        pipeline.analyze_intake(report['id'])
        assert alerts == {f'important-intake:{source}:{pipeline.source_message_key(parent)}'}
        assert notify.call_count == 1
