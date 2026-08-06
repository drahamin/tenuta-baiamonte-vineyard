import asyncio
import json
import logging
import urllib.request

from .config import get_settings
from .service import public_harvest_feed

logger = logging.getLogger(__name__)


def publish_once() -> None:
    settings = get_settings()
    if not settings.public_publish_url:
        return
    body = json.dumps(public_harvest_feed()).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Baiamonte-Vineyard/1.0"}
    if settings.public_publish_token:
        headers["Authorization"] = f"Bearer {settings.public_publish_token}"
    request = urllib.request.Request(settings.public_publish_url, data=body, headers=headers, method="PUT")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status >= 300:
            raise RuntimeError(f"Publish failed with HTTP {response.status}")


async def publishing_loop() -> None:
    settings = get_settings()
    while settings.public_publish_url:
        try:
            await asyncio.to_thread(publish_once)
        except Exception:
            logger.exception("Public harvest feed publish failed")
        await asyncio.sleep(max(1, settings.public_publish_minutes) * 60)

