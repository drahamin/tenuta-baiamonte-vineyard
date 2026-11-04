# Direct-site ordinary-light status v1

Frozen candidate for review, 2026-11-04. Source/test staging only. Not released,
not activated, and not a light-control contract.

Request: `GET /api/baiamonte_mobile/v1/records?object=lights&projection=lights-v1`.
The existing records route and relay are used. Only `object` and `projection`
are accepted, once each. No entity, service, estate, limit or cursor parameter
is accepted. No POST, PUT, PATCH or DELETE method is added.

Authorization: the current session must be Admin with BOTH `records` and the
separate explicit `lights.read` capability. The Admin role ceiling permits
that capability, but neither installation nor an existing Admin session grants
it. The current identity policy is rechecked on every request. Worker, Viewer,
and Enologist are denied. The separate `mobile_lights_status_enabled` option
defaults to false and must also be enabled. Denial occurs before credential
lookup or source I/O. Existing sessions and all other reads remain valid.

Response example (synthetic; `items` always contains the eight reviewed lights):

```json
{
  "contract": "baiamonte.direct-site.v1",
  "projection": "lights-v1",
  "object": "lights",
  "lights": {
    "contract": "baiamonte.mobile-lights.v1",
    "estate_id": "11111111-1111-4111-8111-111111111111",
    "timestamp_basis": "home_assistant_source_report",
    "items": [{
      "entity_id": "light.switch_1_lightbulb",
      "name": "Kitchen overhead",
      "state": "off",
      "reported_at": "2026-11-04T11:59:00Z",
      "data_age_seconds": 60,
      "quality": "current"
    }]
  }
}
```

The shortened sample illustrates one item only. An actual successful response
contains exactly eight unique entity IDs and their fixed names:

| Entity | Name |
| --- | --- |
| `light.switch_1_lightbulb` | Kitchen overhead |
| `light.switch_2_lightbulb` | Warehouse |
| `light.switch_3_lightbulb` | Toilette |
| `light.switch_4_lightbulb` | Palmento |
| `light.switch_5_lightbulb` | Patio |
| `light.switch_6_lightbulb` | Patio strip |
| `light.switch_7_lightbulb` | Kitchen sink |
| `light.switch_8_lightbulb` | Fox Den overhead |

Source is only a GET to each fixed `/core/api/states/<approved entity>` on the
existing Supervisor source. No entity enumeration, history request, service
call or control method is made. Redirects and environment proxies are disabled;
the total source deadline is two seconds, with at most eight concurrent requests
and 16,384 uncompressed bytes per source. Independent completed reads survive a
source timeout. No exception text, token, attributes, brightness, control metadata
or source-supplied name is serialized.

State is `on`, `off`, or null. Only the exact source entity ID and a valid,
timezone-qualified, nonfuture HA `last_reported` clock qualify a status.
`last_updated`, `last_changed`, request time, cache time and installation time
are not substitutes. `reported_at` is normalized to UTC; age is a nonnegative
integer or null. Quality is `current` through 900 seconds, `stale` after that,
or `unavailable` with null state/time/age if the source cannot qualify.
This is a Home Assistant report time, not proof of a physical sensor reading.

There is deliberately no `controllable` field and no `light.control` or other
control grant. Camera/security lights, pseudo-lights, gates, pumps, power and
all other entities are permanently outside this allowlist.

Scope references independently matched before implementation:

- Reviewed website `LightControlService.php`: SHA256
  `46602521f95ead1a2373df8cc8f7aef76b2cd97667c1b07837a421685449b85d`.
- `MOBILE_TELEMETRY_AND_LIGHTING_V1.md`: SHA256
  `c5386004cb43142f4be23e0f55d6aa78a79e37a084d442c566bad3b7e3a325bf`.
- Native `MobileLightCatalog.reviewedLights`: exact eight IDs/names match.

Remaining gates: independent source and DTO review, package/release qualification,
explicit production enablement of this status-only flag and `lights.read` for
the intended existing Admin identity, then an ordinary authenticated session
exchange and read acceptance. No production policy, flag or session has changed.
Existing sessions must not be logged out to install this read capability.
