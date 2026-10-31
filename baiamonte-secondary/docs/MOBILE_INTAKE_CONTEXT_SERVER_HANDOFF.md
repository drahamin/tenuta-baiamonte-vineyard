# Mobile intake context v1

`GET /erp/mobile/v1/intake/context` supplies the server-authoritative estate
boundary and current entity revisions required to build a pending-review mobile
intake report. The client must never hardcode an estate UUID or revision.

The route is available only when mobile authentication and field intake are
enabled. It requires a valid mobile bearer session whose current server role is
`operator` or `admin` and whose token has the exact `intake.submit` capability.
Browser cookies do not authenticate this route.

## Request

Query parameters:

- `entity_type`: exactly one of `block_id`, `task_id`, `work_activity_id`,
  `container_id`, or `wine_lot_id`.
- `limit`: optional integer from 1 through 100; default 50.
- `cursor`: optional opaque continuation value returned by the preceding page.

## Successful response

```json
{
  "ok": true,
  "context_version": 1,
  "estate_id": "server-configured UUID",
  "source": {
    "source_generated_at": "2026-10-20 12:00:00.000000",
    "last_success_at": "2026-10-20 12:00:03.000000",
    "data_age_seconds": 3,
    "state": "ready"
  },
  "entity_type": "container_id",
  "available": true,
  "items": [
    {
      "id": "tank-5",
      "revision": "8",
      "label": "T-05",
      "status": "active",
      "relations": {}
    }
  ],
  "next_cursor": null
}
```

`revision` is always a lossless decimal string copied from the active replica.
The response never includes the internal snapshot ID or raw replica data.
Labels, status, and relations are selected from fixed per-type allowlists.

If an approved entity object is not part of the active reporting contract,
`available` is `false` and `items` is empty. The server never invents IDs or
revisions. If the replica is unavailable, `source.state` is `unavailable`.

A cursor is bound to both the requested entity type and the active snapshot
generation. A cursor cannot be reused for another entity type. If a new
snapshot becomes active between pages, the server returns HTTP 409:

```json
{"ok":false,"error":"intake_context_snapshot_changed"}
```

The client must discard all pages for that entity type and restart discovery.
It must also clear cached context on logout or account change. HA still checks
every submitted entity, relationship, estate, and revision; context discovery
does not approve or apply a production record.
