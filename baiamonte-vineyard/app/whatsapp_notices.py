from __future__ import annotations

from contextvars import ContextVar

from .db import transaction
from .service import estate_id


inbound_context: ContextVar[tuple[str, str | None] | None] = ContextVar("whatsapp_inbound_context", default=None)


def resolve_answered_notice() -> None:
    """Close the question notice after the channel has actually answered it."""
    context = inbound_context.get()
    if not context:
        return
    message_id, record_id = context
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE alerts SET status='resolved',resolved_at=NOW() WHERE estate_id=%s AND status IN ('open','acknowledged') AND source_id=%s",
            (estate_id(), f"important-intake:whatsapp:{message_id}"),
        )
        if record_id:
            cursor.execute(
                "UPDATE alerts SET status='resolved',resolved_at=NOW() WHERE estate_id=%s AND status IN ('open','acknowledged') AND JSON_UNQUOTE(JSON_EXTRACT(metadata,'$.intake_id'))=%s",
                (estate_id(), record_id),
            )
            cursor.execute(
                "UPDATE intake_items SET review_status='archived',review_reason='Conversation answered; no database action required',reviewed_by='WhatsApp assistant',reviewed_at=NOW(),archived_at=NOW() "
                "WHERE id=%s AND estate_id=%s AND source='whatsapp' AND classification='other' AND review_status='ready_for_review' "
                "AND COALESCE(JSON_LENGTH(JSON_EXTRACT(extracted_data,'$.facts')),0)=0 AND COALESCE(JSON_LENGTH(JSON_EXTRACT(extracted_data,'$.suggested_database_records')),0)=0",
                (record_id, estate_id()),
            )


def mark_intervention_notice() -> None:
    """Keep only a deliberately marked item in the Today intervention queue."""
    context = inbound_context.get()
    if not context:
        return
    message_id, record_id = context
    source_id = f"important-intake:whatsapp:{message_id}"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE alerts SET status='open',resolved_at=NULL,title='Action needed',metadata=JSON_SET(COALESCE(metadata,JSON_OBJECT()),'$.intervention_required',TRUE) WHERE estate_id=%s AND source_id=%s",
            (estate_id(), source_id),
        )
        if record_id:
            cursor.execute(
                "UPDATE alerts SET status='open',resolved_at=NULL,title='Action needed',metadata=JSON_SET(COALESCE(metadata,JSON_OBJECT()),'$.intervention_required',TRUE) WHERE estate_id=%s AND JSON_UNQUOTE(JSON_EXTRACT(metadata,'$.intake_id'))=%s",
                (estate_id(), record_id),
            )


def reconcile_answered_notices() -> int:
    """Remove handled channel notices and non-vineyard email questions from Today."""
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE alerts a JOIN intake_items i ON i.estate_id=a.estate_id AND i.id=JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intake_id')) "
            "SET a.status='resolved',a.resolved_at=NOW() WHERE a.estate_id=%s AND a.status IN ('open','acknowledged') "
            "AND a.source_id LIKE 'important-intake:whatsapp:%%' AND ((a.title='Question needs reply' AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intervention_required')),'false')<>'true') "
            "OR i.review_status IN ('approved','rejected','archived') OR EXISTS (SELECT 1 FROM integration_events e WHERE e.estate_id=a.estate_id "
            "AND e.integration_name='whatsapp-channel' AND e.direction='outbound' AND e.external_id=SUBSTRING_INDEX(i.external_id,':',1) AND e.status='processed' "
            "AND e.event_type IN ('chatbot_reply','manager_camera_snapshot','inbound_routing')))",
            (estate_id(),),
        )
        resolved = int(cursor.rowcount or 0)
        cursor.execute(
            "UPDATE alerts a JOIN intake_items i ON i.estate_id=a.estate_id AND i.id=JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intake_id')) "
            "SET a.status='resolved',a.resolved_at=NOW() WHERE a.estate_id=%s AND a.status IN ('open','acknowledged') "
            "AND a.source_id LIKE 'important-intake:gmail:%%' AND a.title='Question needs reply' AND COALESCE(i.classification,'other')='other'",
            (estate_id(),),
        )
        return resolved + int(cursor.rowcount or 0)
