import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.domains import mobile_intake_policy


AUTHOR_USER = "22456456-cc5e-11f1-b520-0200fd82860d"
AUTHOR_HA = "50302bdc5bed42ac92dbfc2b4b4e5181"


def configured(monkeypatch):
    monkeypatch.setattr(mobile_intake_policy, "runtime_option", lambda *_: {
        "enabled": True,
        "website_user_id": AUTHOR_USER,
        "website_username": "david",
        "ha_user_id": AUTHOR_HA,
        "ha_username": "rahamin",
        "allowed_kinds": ["enology_reading"],
    })
    return mobile_intake_policy.MobileIntakeAuthorPolicy.current()


def request(username: str, user_id: str, *, client="172.30.32.2", ingress="/api/hassio_ingress/mobile", extra=()) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "client": (client, 1234), "headers": [(b"x-ingress-path", ingress.encode()), (b"x-remote-user-name", username.encode()), (b"x-remote-user-id", user_id.encode()), *extra]})


def test_exact_david_website_to_ha_mapping_is_allowed(monkeypatch):
    policy = configured(monkeypatch)
    assert policy.require_author_request(request("rahamin", AUTHOR_HA)) == "david"
    assert policy.sync_actor_is_author({"user_id": AUTHOR_USER, "username": "david", "ha_user_id": AUTHOR_HA}, "enology_reading")


@pytest.mark.parametrize("username,user_id", [
    ("sebastian", "f402bf2ae76842088ac296979a9f4a8e"),
    ("operator", AUTHOR_HA),
    ("rahamin", "11432746818f436a99e32d11801f5766"),
])
def test_known_names_roles_and_mismatched_ids_are_denied(monkeypatch, username, user_id):
    policy = configured(monkeypatch)
    with pytest.raises(HTTPException) as denied:
        policy.require_author_request(request(username, user_id))
    assert denied.value.status_code == 403


@pytest.mark.parametrize("candidate", [
    request("rahamin", AUTHOR_HA, client="203.0.113.10"),
    request("rahamin", AUTHOR_HA, ingress="/forged/proxy"),
    request("rahamin", AUTHOR_HA, extra=((b"x-remote-user-id", AUTHOR_HA.encode()),)),
    request("rahamin", AUTHOR_HA, extra=((b"x-remote-user-name", b"rahamin"),)),
    request("rahamin", AUTHOR_HA, extra=((b"x-ingress-path", b"/api/hassio_ingress/duplicate"),)),
])
def test_forged_proxy_and_duplicate_identity_headers_are_denied(monkeypatch, candidate):
    policy = configured(monkeypatch)
    with pytest.raises(HTTPException) as denied:
        policy.require_author_request(candidate)
    assert denied.value.status_code == 403


def test_policy_is_default_off_and_review_is_unavailable(monkeypatch):
    monkeypatch.setattr(mobile_intake_policy, "runtime_option", lambda *_: {})
    with pytest.raises(HTTPException) as disabled:
        mobile_intake_policy.MobileIntakeAuthorPolicy.current()
    assert disabled.value.status_code == 503
    with pytest.raises(HTTPException) as review:
        mobile_intake_policy.review_unavailable()
    assert review.value.status_code == 503
