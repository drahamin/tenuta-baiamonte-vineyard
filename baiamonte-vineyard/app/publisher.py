import json
import logging
import urllib.request

from .config import get_settings
from .db import transaction
from .service import estate_id, public_harvest_feed

logger = logging.getLogger(__name__)


def _record_publish(status: str, *, error: str | None = None, item_count: int | None = None) -> None:
    """Keep a safe operational trail without storing tokens or the public payload."""
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload,error_message) "
                "VALUES (%s,'public-harvest-publisher','outbound','harvest_feed_publish',%s,%s,%s)",
                (estate_id(), status, json.dumps({"item_count": item_count}) if item_count is not None else None, error[:1000] if error else None),
            )
            if status == "processed":
                cursor.execute(
                    "INSERT INTO sync_checkpoints (estate_id,integration_name,checkpoint_value,last_success_at,last_attempt_at,last_error,metadata) "
                    "VALUES (%s,'public_harvest_publisher',UTC_TIMESTAMP(),UTC_TIMESTAMP(),UTC_TIMESTAMP(),NULL,%s) "
                    "ON DUPLICATE KEY UPDATE checkpoint_value=VALUES(checkpoint_value),last_success_at=UTC_TIMESTAMP(),last_attempt_at=UTC_TIMESTAMP(),last_error=NULL,metadata=VALUES(metadata)",
                    (estate_id(), json.dumps({"item_count": item_count})),
                )
            else:
                cursor.execute(
                    "INSERT INTO sync_checkpoints (estate_id,integration_name,last_attempt_at,last_error) "
                    "VALUES (%s,'public_harvest_publisher',UTC_TIMESTAMP(),%s) "
                    "ON DUPLICATE KEY UPDATE last_attempt_at=UTC_TIMESTAMP(),last_error=VALUES(last_error)",
                    (estate_id(), error[:1000] if error else "Publish failed"),
                )
    except Exception:
        logger.exception("Could not record public harvest publishing status")


def publish_once() -> None:
    settings = get_settings()
    if not settings.public_publish_url:
        return
    feed = public_harvest_feed()
    body = json.dumps(feed).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Baiamonte-Vineyard/1.0"}
    if settings.public_publish_token:
        headers["Authorization"] = f"Bearer {settings.public_publish_token}"
        # Some shared hosts remove Authorization before PHP receives it.
        # Keep the standard bearer header and add a dedicated fallback.
        headers["X-Vineyard-Token"] = settings.public_publish_token
    request = urllib.request.Request(settings.public_publish_url, data=body, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 300:
                raise RuntimeError(f"Publish failed with HTTP {response.status}")
    except Exception as error:
        _record_publish("failed", error=str(error))
        raise
    _record_publish("processed", item_count=len(feed.get("items") or []))
