"""Pure preparation of an already captured consistent read, not a DB adapter.

No source fetch, clock fabrication, reporting-revision creation, grant or endpoint.
A future qualified adapter must supply complete estate-scoped reporting rows
from one bounded read-only snapshot and verified reporting change tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import UUID

from .mobile_work_review_projection import (
    DATASETS, MAX_INPUT_ROWS, SourceUnavailable, _ID, _REVISION, _iso, _safe_data, _utc,
)


GENERATION_SCHEME = "baiamonte.work-review.consistent-read-generation.v1"


@dataclass(frozen=True)
class PreparedSnapshotInput:
    generation: str
    object_name: str
    records: tuple[Mapping[str, Any], ...]


def prepare_snapshot_input(
    records: Sequence[Mapping[str, Any]], *, estate_id: str,
    view: str, dataset: str,
) -> PreparedSnapshotInput:
    """Validate/freeze rows without inventing a source revision or event time.

    This function does not authenticate its caller or prove SQL isolation.
    Missing/duplicate scoped logical identity fails the entire dataset, even
    if that row would fall outside a requested page or state filter.
    """
    if not isinstance(estate_id, str) or str(UUID(estate_id)) != estate_id:
        raise ValueError("invalid estate boundary")
    if not isinstance(view, str) or not isinstance(dataset, str) or (view, dataset) not in DATASETS:
        raise ValueError("invalid dataset")
    if len(records) > MAX_INPUT_ROWS:
        raise SourceUnavailable("input exceeds complete snapshot bound")
    object_name, fields = DATASETS[view, dataset]
    captured, seen = [], set()
    for record in records:
        if not isinstance(record, Mapping) or record.get("object") != object_name:
            raise SourceUnavailable("source object scope mismatch")
        data = record.get("data")
        if not isinstance(data, Mapping) or data.get("estate_id") != estate_id:
            raise SourceUnavailable("source estate scope mismatch")
        identifier = data.get("sample_id") if object_name == "ro_lab_decision_queue" else data.get("id")
        if not isinstance(identifier, str) or _ID.fullmatch(identifier) is None or identifier in seen:
            raise SourceUnavailable("missing or duplicate logical identity")
        if object_name != "ro_lab_decision_queue" and record.get("id") != identifier:
            raise SourceUnavailable("reporting identity mismatch")
        revision = record.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, (str, int)) or _REVISION.fullmatch(str(revision)) is None:
            raise SourceUnavailable("invalid reporting token")
        seen.add(identifier)
        updated = _iso(_utc(record.get("source_updated_at")))
        safe = _safe_data(data, fields)
        if object_name == "ro_lab_decision_queue" and "needs_review" in data:
            flag = data["needs_review"]
            # Preserve unknown internally for conservative filtering; otherwise
            # omitting null would turn it into the missing/false default.
            safe["needs_review"] = (flag.strip()[:160] if isinstance(flag, str) else flag) if isinstance(flag, (str, bool, int)) or isinstance(flag, float) and math.isfinite(flag) else None
        captured.append({"object": object_name, "id": identifier, "revision": str(revision),
                         "source_updated_at": updated, "data": {"estate_id": estate_id, **safe}})
    captured.sort(key=lambda row: row["id"])
    # Include exact captured output and supplied full-reporting tokens, including
    # date-derived view values. Exclude retrieval clocks and random export UUIDs.
    raw = json.dumps([GENERATION_SCHEME, estate_id, view, dataset, captured],
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    generation = hashlib.sha256(raw.encode()).hexdigest()
    frozen = tuple(MappingProxyType({**row, "data": MappingProxyType(row["data"])}) for row in captured)
    return PreparedSnapshotInput(generation, object_name, frozen)
