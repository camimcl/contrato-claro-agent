from types import SimpleNamespace

import requests

from contratoclaro.provider import MantleClient


class Credentials:
    def get_frozen_credentials(self):
        return SimpleNamespace(access_key="key", secret_key="secret", token=None)


class Session:
    def get_credentials(self):
        return Credentials()


class Ledger:
    def reserve(self, *_args):
        return "reservation"

    def settle(self, *_args, **_kwargs):
        return None


def test_retries_one_connect_timeout_before_succeeding(monkeypatch):
    monkeypatch.setattr("contratoclaro.provider.boto3.Session", lambda **_kwargs: Session())
    client = MantleClient(ledger=Ledger())
    attempts = []

    def post(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise requests.exceptions.ConnectTimeout("not connected")
        return SimpleNamespace(ok=True, json=lambda: {"usage": {"input_tokens": 1, "output_tokens": 1}})

    monkeypatch.setattr("contratoclaro.provider.requests.post", post)
    monkeypatch.setattr("contratoclaro.provider.time.sleep", lambda _seconds: None)
    assert client.respond({"instructions": "x", "input": "x"})["usage"]["input_tokens"] == 1
    assert len(attempts) == 2
