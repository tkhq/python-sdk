"""Offline tests for send_signed_request result flattening.

These mock ``requests.post`` and use a stub stamper, so they need no credentials
and make no network calls. They do not use the fixtures in ``conftest.py``.
"""

from typing import Any, Dict

from turnkey_api_key_stamper import TStamp
from turnkey_sdk_types import (
    EthSendTransactionBody,
    EthSendTransactionResponse,
    SignTransactionBody,
    SignTransactionResponse,
)
from turnkey_http.generated import client as client_module
from turnkey_http.generated.client import TurnkeyClient

ORG_ID = "org-123"
ADDRESS = "0x0000000000000000000000000000000000000001"


class StubStamper:
    def stamp(self, body: str) -> TStamp:
        return TStamp(stamp_header_name="X-Stamp", stamp_header_value="stub")


class FakeResponse:
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.ok = True
        self.status_code = 200
        self.reason = "OK"
        self.text = ""

    def json(self) -> Dict[str, Any]:
        return self._data


def completed(activity_type: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "activity": {
            "id": "activity-1",
            "organizationId": ORG_ID,
            "status": "ACTIVITY_STATUS_COMPLETED",
            "type": activity_type,
            "intent": {},
            "result": result,
            "votes": [],
            "fingerprint": "fingerprint",
            "canApprove": False,
            "canReject": False,
            "createdAt": {"seconds": "0", "nanos": "0"},
            "updatedAt": {"seconds": "0", "nanos": "0"},
        }
    }


def make_client(monkeypatch, payload: Dict[str, Any]) -> TurnkeyClient:
    monkeypatch.setattr(
        client_module.requests,
        "post",
        lambda url, headers=None, data=None, timeout=None: FakeResponse(payload),
    )
    return TurnkeyClient(
        base_url="https://api.example.test",
        stamper=StubStamper(),  # type: ignore[arg-type]
        organization_id=ORG_ID,
    )


def eth_send_body() -> EthSendTransactionBody:
    # "from" is a Python keyword, so the model takes it by alias.
    return EthSendTransactionBody.model_validate(
        {
            "from": ADDRESS,
            "caip2": "eip155:8453",
            "calls": [{"to": ADDRESS, "value": "1"}],
        }
    )


def test_typed_send_signed_request_flattens_a_versioned_result_key(monkeypatch):
    payload = completed(
        "ACTIVITY_TYPE_ETH_SEND_TRANSACTION_V2",
        {"ethSendTransactionResultV2": {"sendTransactionStatusId": "sts-1"}},
    )
    client = make_client(monkeypatch, payload)

    signed = client.stamp_eth_send_transaction(eth_send_body())
    response = client.send_signed_request(signed, EthSendTransactionResponse)

    assert response.sendTransactionStatusId == "sts-1"
    assert response.activity.status == "ACTIVITY_STATUS_COMPLETED"


def test_untyped_send_signed_request_flattens_a_versioned_result_key(monkeypatch):
    payload = completed(
        "ACTIVITY_TYPE_ETH_SEND_TRANSACTION_V2",
        {"ethSendTransactionResultV2": {"sendTransactionStatusId": "sts-1"}},
    )
    client = make_client(monkeypatch, payload)

    signed = client.stamp_eth_send_transaction(eth_send_body())
    raw = client.send_signed_request(signed)

    assert raw["sendTransactionStatusId"] == "sts-1"
    assert raw["activity"]["id"] == "activity-1"


def test_send_signed_request_still_flattens_an_unversioned_result_key(monkeypatch):
    payload = completed(
        "ACTIVITY_TYPE_SIGN_TRANSACTION_V2",
        {"signTransactionResult": {"signedTransaction": "02abcd"}},
    )
    client = make_client(monkeypatch, payload)

    signed = client.stamp_sign_transaction(
        SignTransactionBody(
            signWith=ADDRESS,
            unsignedTransaction="02ef",
            type="TRANSACTION_TYPE_ETHEREUM",
        )
    )
    response = client.send_signed_request(signed, SignTransactionResponse)

    assert response.signedTransaction == "02abcd"


def test_default_polling_budget_covers_slow_activities():
    client = TurnkeyClient(
        base_url="https://api.example.test",
        stamper=StubStamper(),  # type: ignore[arg-type]
        organization_id=ORG_ID,
    )

    assert client.polling_interval_ms * client.max_polling_retries >= 10_000
