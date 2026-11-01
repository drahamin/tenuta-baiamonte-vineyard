"""Source-disabled first-flow review decision and reliable result delivery.

This module is intentionally not imported by the running application.  The
author and eligible reviewers must come from an explicit owner-approved runtime
policy; no account inherits review authority merely by existing in HA.  A
decision never applies a cellar or inventory mutation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import runtime_option
from ..db import fetch_all, transaction
from ..mobile_intake_sync import RemoteIntakeConfig, _intake_signed_post
from ..remote_erp import _canonical
from ..service import audit, estate_id, new_id


CONTRACT = "baiamonte.mobile-intake-review.v1"
INITIAL_KIND = "enology_reading"
DECISIONS = {"approved", "rejected", "correction_required"}


class ReviewRejected(ValueError):
    pass


class ReviewConflict(Exception):
    pass


@dataclass(frozen=True)
class ReviewerBinding:
    ha_user_id: str
    role: str
    capabilities: frozenset[str]


@dataclass(frozen=True)
class ReviewPolicy:
    author_website_user_id: str
    author_username: str
    author_ha_user_id: str
    author_ha_username: str
    reviewers: dict[str, ReviewerBinding]
    entry_kind: str = INITIAL_KIND

    @classmethod
    def current(cls) -> "ReviewPolicy":
        raw = runtime_option("remote_mobile_intake_review_policy", {})
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            raise ReviewRejected("review_policy_not_configured")
        author = raw.get("author")
        kind = str(raw.get("entry_kind") or "").strip()
        configured = raw.get("reviewers")
        approval_id = str(raw.get("owner_approval_id") or "")
        if not isinstance(author, dict) or kind != INITIAL_KIND or not isinstance(configured, dict) or not _uuid4(approval_id):
            raise ReviewRejected("review_policy_not_configured")
        author_binding = (
            str(author.get("website_user_id") or "").strip().lower(),
            str(author.get("website_username") or "").strip().casefold(),
            str(author.get("ha_user_id") or "").strip().lower(),
            str(author.get("ha_username") or "").strip().casefold(),
        )
        if not _uuid(author_binding[0]) or not _ha_id(author_binding[2]) or not author_binding[1] or not author_binding[3]:
            raise ReviewRejected("review_policy_not_configured")
        reviewers: dict[str, ReviewerBinding] = {}
        for name, value in configured.items():
            username = str(name).strip().casefold()
            if not username or not isinstance(value, dict):
                continue
            user_id = str(value.get("ha_user_id") or "").strip().lower()
            role = str(value.get("role") or "").strip()
            capabilities = frozenset(str(item).strip() for item in value.get("capabilities") or [] if str(item).strip())
            if _ha_id(user_id) and role and capabilities:
                reviewers[username] = ReviewerBinding(user_id, role, capabilities)
        if not reviewers:
            raise ReviewRejected("review_policy_not_configured")
        return cls(*author_binding, reviewers, kind)

    def reviewer(self, username: str, ha_user_id: str, capability: str) -> ReviewerBinding | None:
        binding = self.reviewers.get(username.strip().casefold())
        return binding if binding and binding.ha_user_id == ha_user_id.strip().lower() and capability in binding.capabilities else None


def decide_initial_enology_report(
    report_uuid: str,
    expected_revision: int,
    review_status: str,
    review_note: str,
    reviewer_username: str,
    reviewer_ha_user_id: str,
    reviewer_role: str,
    policy: ReviewPolicy,
) -> dict[str, Any]:
    """Persist one independent human decision and its outbound receipt atomically."""
    reviewer = reviewer_username.strip().casefold()
    note = review_note.strip()
    binding = policy.reviewer(reviewer, reviewer_ha_user_id, "mobile_intake.enology.review")
    if policy.entry_kind != INITIAL_KIND or not binding or binding.role != reviewer_role:
        raise ReviewRejected("initial_enology_reviewer_not_authorized")
    if review_status not in DECISIONS or not note or len(note) > 2000:
        raise ReviewRejected("review_decision_invalid")
    if not isinstance(expected_revision, int) or expected_revision < 1:
        raise ReviewRejected("expected_revision_invalid")
    decision_uuid = new_id()
    reviewed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT report_uuid,actor_username,entry_kind,status,revision FROM mobile_intake_source_drafts "
            "WHERE report_uuid=%s AND estate_id=%s FOR UPDATE",
            (report_uuid, estate_id()),
        )
        row = cursor.fetchone()
        if not row:
            raise ReviewRejected("mobile_intake_report_not_found")
        author = str(row.get("actor_username") or "").casefold()
        if author != policy.author_username or row.get("entry_kind") != policy.entry_kind:
            raise ReviewRejected("report_outside_initial_activation_scope")
        if reviewer == author:
            raise ReviewRejected("independent_reviewer_required")
        if int(row.get("revision") or 0) != expected_revision or row.get("status") != "pending_review":
            raise ReviewConflict("mobile_intake_revision_conflict")
        next_revision = expected_revision + 1
        decision = {
            "contract": CONTRACT,
            "decision_uuid": decision_uuid,
            "report_uuid": report_uuid,
            "review_status": review_status,
            "review_revision": str(next_revision),
            "reviewed_at": reviewed_at,
            "review_note": note,
            "reviewer": {"username": reviewer, "ha_user_id": binding.ha_user_id, "role": reviewer_role},
            "business_application_status": "not_applied",
            "domain_side_effects": [],
        }
        canonical = _canonical(decision)
        changed = cursor.execute(
            "UPDATE mobile_intake_source_drafts SET status=%s,revision=%s,reviewed_by=%s,reviewed_at=%s,review_note=%s "
            "WHERE report_uuid=%s AND estate_id=%s AND revision=%s AND status='pending_review'",
            (review_status, next_revision, reviewer, reviewed_at.replace("T", " ").removesuffix("Z"), note, report_uuid, estate_id(), expected_revision),
        )
        if changed != 1:
            raise ReviewConflict("mobile_intake_revision_conflict")
        cursor.execute(
            "INSERT INTO mobile_intake_review_outbox(decision_uuid,report_uuid,estate_id,payload_sha256,payload_json,status,next_attempt_at) "
            "VALUES(%s,%s,%s,%s,%s,'pending',NOW(6))",
            (decision_uuid, report_uuid, estate_id(), hashlib.sha256(canonical.encode()).hexdigest(), canonical),
        )
        audit(cursor, "review", "mobile_intake_draft", report_uuid, decision, reviewer)
    return {**decision, "delivery_status": "pending"}


def _uuid4(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value, re.I) is not None


def _uuid(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value, re.I) is not None


def _ha_id(value: str) -> bool:
    import re
    return re.fullmatch(r"[0-9a-f]{32}", value, re.I) is not None


def deliver_review_decisions_once(config: RemoteIntakeConfig | None = None, limit: int = 10) -> int:
    """Deliver pending receipts outbound; exact retries are website-idempotent."""
    config = config or RemoteIntakeConfig.current()
    if not config.enabled:
        return 0
    config.validate()
    rows = fetch_all(
        "SELECT decision_uuid,report_uuid,payload_json FROM mobile_intake_review_outbox "
        "WHERE estate_id=%s AND status='pending' AND next_attempt_at<=NOW(6) ORDER BY created_at LIMIT %s",
        (estate_id(), max(1, min(20, limit))),
    )
    delivered = 0
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        response = _intake_signed_post(config, f"/sync/mobile-intake/reviews/{row['report_uuid']}", payload, 30)
        if response.get("ok") is not True:
            continue
        with transaction() as (_, cursor):
            changed = cursor.execute(
                "UPDATE mobile_intake_review_outbox SET status='delivered',delivered_at=NOW(6),attempts=attempts+1 "
                "WHERE decision_uuid=%s AND status='pending'",
                (row["decision_uuid"],),
            )
            delivered += int(changed == 1)
    return delivered
