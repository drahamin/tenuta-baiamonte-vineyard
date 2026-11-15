import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request
from app.domains import alerts_intake_routes as routes
from app.intake_scope import source_message_key
from app.mcp_server import intake_review_detail


@pytest.fixture
def database():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.create_function('JSON_UNQUOTE', 1, lambda value: value)
    db.create_function('NOW', 0, lambda: '2026-11-15T12:00:00')
    columns = ('id estate_id source external_id sender_name sender_address received_at title message_text '
               'source_metadata original_filename stored_path file_sha256 media_type classification ai_summary '
               'extracted_data review_status review_reason reviewed_by reviewed_at processing_error archived_at').split()
    db.execute('CREATE TABLE intake_items (' + ','.join(name + ' TEXT' for name in columns) + ')')
    def execute(sql, params=()):
        return db.execute(sql.replace('%s', '?'), params)
    def one(sql, params=()):
        row = execute(sql, params).fetchone()
        return dict(row) if row else None
    def all_rows(sql, params=()):
        return [dict(row) for row in execute(sql, params).fetchall()]
    @contextmanager
    def transaction():
        yield db, SimpleNamespace(execute=execute)
    def add(external, source='whatsapp', estate='estate-1', **values):
        row = dict(id=str(uuid4()), estate_id=estate, source=source, external_id=external,
                   received_at='2026-11-15T10:00:00', source_metadata='{}', original_filename='message.txt',
                   review_status='ready_for_review')
        row.update(values)
        execute('INSERT INTO intake_items (' + ','.join(row) + ') VALUES (' + ','.join(['%s'] * len(row)) + ')', tuple(row.values()))
        return row['id']
    with patch.object(routes, 'estate_id', return_value='estate-1'), \
         patch.object(routes, 'fetch_one', side_effect=one), \
         patch.object(routes, 'fetch_all', side_effect=all_rows), \
         patch.object(routes, 'transaction', transaction):
        yield add, one
    db.close()


def ids(item):
    return {row['id'] for row in item['related_items']}


def test_system_account_messages_remain_independent_in_http_and_mcp(database):
    add, _ = database
    first = add('system-wa:1:message-A')
    add('system-wa:1:message-B')
    add('system-wa:2:message-A')
    add('system-wa:1:message-A', estate='estate-2')
    assert ids(routes.intake_detail(first)) == set()
    assert ids(intake_review_detail(first)) == set()


def test_opaque_codex_ids_and_atomic_system_ids_are_never_split(database):
    add, _ = database
    item = add('conversation:body', source='codex')
    add('conversation:attachment-0', source='codex')
    assert ids(routes.intake_detail(item)) == set()
    assert source_message_key({'id': item, 'source': 'whatsapp', 'external_id': 'system-wa:1:message:body'}) == 'system-wa:1:message:body'
    assert source_message_key({'id': item, 'source': 'whatsapp', 'external_id': 'system-wa:1:other'}) != source_message_key({'id': item, 'source': 'whatsapp', 'external_id': 'system-wa:1:message'})


@pytest.mark.parametrize('source,base', [('gmail', 'gmail-hash'), ('whatsapp', 'wamid.exact')])
def test_known_message_parts_keep_their_real_siblings_only(database, source, base):
    add, _ = database
    body = add(base + ':body', source=source)
    pdf = add(base + ':attachment-0', source=source)
    add(base + ':attachment-0:unexpected', source=source)
    add(base + '-other:attachment-0', source=source)
    add(base + ':attachment-1', source=source, estate='estate-2')
    add(base + ':attachment-1', source='codex')
    assert ids(routes.intake_detail(body)) == {pdf}
    assert ids(routes.intake_detail(pdf)) == {body}


def test_sql_like_metacharacters_in_message_ids_are_literal(database):
    add, _ = database
    body = add('gmail-%_!:body', source='gmail')
    pdf = add('gmail-%_!:attachment-0', source='gmail')
    add('gmail-AB!:attachment-1', source='gmail')
    assert ids(routes.intake_detail(body)) == {pdf}


def test_recovered_report_uses_exact_parent_even_with_legacy_bad_external_id(database):
    add, _ = database
    parent = add('system-wa:1:message-A')
    other = add('system-wa:1:message-B')
    report = add('system-wa:1:manual-report-aaaa', source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': parent}))
    add('system-wa:1:manual-report-bbbb', source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': other}))
    add('system-wa:1:manual-report-cccc', estate='estate-2', source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': parent}))
    add('system-wa:1:manual-report-dddd', source_metadata='not-json')
    assert ids(routes.intake_detail(parent)) == {report}
    assert ids(routes.intake_detail(report)) == {parent}


def test_parent_reference_cannot_cross_estate_or_source(database):
    add, _ = database
    foreign = add('secret-message', estate='estate-2')
    child = add('recovered', source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': foreign}))
    assert ids(routes.intake_detail(child)) == set()
    gmail = add('gmail-exact:body', source='gmail')
    child2 = add('recovered2', source_metadata=json.dumps({'attachment_recovery': True, 'manually_attached_to': gmail}))
    assert ids(routes.intake_detail(child2)) == set()


@pytest.mark.parametrize('source,report_external,body_external,should_archive', [
    ('gmail', 'gmail-exact:attachment-0', 'gmail-exact:body', True),
    ('whatsapp', 'system-wa:1:report-A', 'system-wa:1:message-B', False),
])
def test_lab_approval_never_archives_another_message(database, source, report_external, body_external, should_archive):
    add, one = database
    report = add(report_external, source=source, classification='lab_report', media_type='application/pdf')
    body = add(body_external, source=source)
    other = add('system-wa:1:unrelated' if source == 'whatsapp' else 'gmail-other:body', source=source)
    sample = SimpleNamespace(vintage_year=2026, lab_date=date(2026, 11, 15), sample_name='sample', sample_type='wine', results=[1])
    request = Request({'type': 'http', 'headers': [(b'x-remote-user-name', b'tester')]})
    with patch.object(routes, '_lab_payloads', return_value=[sample]), \
         patch.object(routes, 'create_lab_sample', return_value={'id': 'lab-id'}), \
         patch.object(routes, 'link_intake_to_record'), patch.object(routes, 'audit'):
        routes.approve_full_lab_report(report, request, BackgroundTasks())
    assert one('SELECT review_status FROM intake_items WHERE id=%s', (report,))['review_status'] == 'approved'
    assert one('SELECT review_status FROM intake_items WHERE id=%s', (body,))['review_status'] == ('archived' if should_archive else 'ready_for_review')
    assert one('SELECT review_status FROM intake_items WHERE id=%s', (other,))['review_status'] == 'ready_for_review'
