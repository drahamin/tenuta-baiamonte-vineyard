# Native mobile Work and Review read contract v1

Status: frozen for independent review; not deployed.

Both routes use the existing `com.cantinabaiamonte.vineyard` bearer session
and `replica.read` scope. They accept no browser cookie, object name, SQL,
estate/user identifier, or write payload.

## Routes and roles

- `GET /erp/mobile/v1/work`: operator/admin; datasets `tasks`, `activities`,
  `open`, `issues`.
- `GET /erp/mobile/v1/review`: admin; datasets `queue`, `history`.

The closed query set is `dataset`, `state`, `limit`, `cursor`. `dataset` is
required. Work states are `all|open|completed` (default `open`); Review states
are `all|pending|completed` (default `pending`). Limit defaults to 50 and is
bounded to 1–100. The opaque cursor is at most 512 bytes and binds contract
version, snapshot generation, route, dataset, state and binary-sorted record
ID. It cannot cross a snapshot, route, dataset or filter.

## Success DTO

```json
{
  "ok": true,
  "contract": "baiamonte.mobile-work-review.v1",
  "view": "work",
  "dataset": "tasks",
  "estate_id": "00000000-0000-4000-8000-000000000001",
  "source": {
    "source_generated_at": "2026-10-31 22:43:20.000000",
    "last_success_at": "2026-10-31 22:44:01.000000",
    "data_age_seconds": 120,
    "state": "ready"
  },
  "available": true,
  "filters": {"state": "open"},
  "items": [{
    "id": "task-1",
    "revision": "9007199254740993",
    "source_updated_at": "2026-10-31 20:00:00.000000",
    "data": {"title": "Inspect terraces", "status": "planned"}
  }],
  "next_cursor": null
}
```

Revisions are strings. Missing fields stay absent. A permitted but unavailable
dataset returns HTTP 200, `available=false`, explicit source freshness and no
items.

## Field allowlists

- Work/tasks: `title`, `status`, `priority`, `due_date`, `completed_at`,
  `category`, `block_id`, `season_id`, `estimated_hours`.
- Work/activities: `title`, `status`, `category`, `activity_date`, `end_date`,
  `block_id`, `task_id`, `season_id`, `labor_hours`, `worker_count`.
- Work/open: `title`, `status`, `priority`, `due_date`, `days_until_due`,
  `category`, `block_code`, `block_name`.
- Work/issues: `issue_text`, `issue_type`, `subject_ref`, `status`, `priority`,
  `opened_date`, `due_date`, `closed_date`, `decision_action`.
- Review/queue: `sample_id`, `sample_name`, `sample_type`, `lab_date`,
  `result_count`, `flagged_results`, `needs_review`, `review_status`,
  `next_check_at`.
- Review/history: `sample_id`, `decision_type`, `review_status`,
  `decision_action`, `interpretation`, `enologist_approval_required`,
  `approved_at`, `next_check_at`, `created_at`, `updated_at`.

Every row must match the server estate UUID. Assignee/approver IDs, owner
fields, notes, contacts, payroll/cost details, raw/nested data and unlisted
fields are excluded.

## Errors

- 401 `authentication_required`: bearer invalid, expired, revoked or limited.
- 403 `mobile_role_not_permitted`: authenticated role cannot read the view.
- 409 `mobile_read_snapshot_changed`: cursor snapshot is no longer active.
- 422 `invalid_mobile_work_review_request`: invalid dataset/filter/limit/cursor
  or cursor/request mismatch.

This adds no capability, command, intake, camera, directory, location,
payroll, finance, device or power access. App navigation must show Work only
for operator/admin and Review only for admin. A 403 is an unavailable state,
not a prompt for broader scope.
