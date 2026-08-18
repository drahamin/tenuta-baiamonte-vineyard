from email.message import Message

import pytest

from app import publisher


class _Response:
    def __init__(self, *, status=200, content_type="text/html; charset=UTF-8", body=b"<html>ok</html>"):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self._body


def test_public_site_url_uses_origin():
    assert publisher._public_site_url("https://tenutabaiamonte.com/vineyard-feed.php") == "https://tenutabaiamonte.com/"


def test_verify_public_site_requires_html(monkeypatch):
    monkeypatch.setattr(publisher.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(content_type="application/json"))

    with pytest.raises(RuntimeError, match="invalid page"):
        publisher._verify_public_site("https://tenutabaiamonte.com/vineyard-feed.php")


def test_verify_public_site_accepts_renderable_homepage(monkeypatch):
    monkeypatch.setattr(publisher.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response())

    publisher._verify_public_site("https://tenutabaiamonte.com/vineyard-feed.php")
