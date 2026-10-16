"""Offline tests for activity outcome handling.

These tests mock ``requests.post`` and use a stub stamper, so they need no
credentials and make no network calls. They do not use the fixtures in
``conftest.py``.
"""

from typing import Any, Dict, List, Optional

import pytest
from pydantic import ValidationError
from turnkey_api_key_stamper import TStamp
from turnkey_sdk_types import (
    CreateSubOrganizationResponse,
    CreateWalletBody,
    RequestType,
    SignedRequest,
    TurnkeyActivityConsensusNeededError,
    TurnkeyActivityError,
    TurnkeyErrorCodes,
)
from turnkey_http.generated import client as client_module
from turnkey_http.generated.client import TurnkeyClient

ACTIVITY_ID = "activity-123"
ORG_ID = "org-123"


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


def activity_payload(
    status: str,
    result: Optional[Dict[str, Any]] = None,
    failure: Optional[Dict[str, Any]] = None,
    activity_type: str = "ACTIVITY_TYPE_CREATE_WALLET",
) -> Dict[str, Any]:
    activity: Dict[str, Any] = {
        "id": ACTIVITY_ID,
        "organizationId": ORG_ID,
        "status": status,
        "type": activity_type,
        "intent": {},
        "result": result or {},
        "votes": [],
        "fingerprint": "fingerprint",
        "canApprove": False,
        "canReject": False,
        "createdAt": {"seconds": "0", "nanos": "0"},
        "updatedAt": {"seconds": "0", "nanos": "0"},
    }
    if failure is not None:
        activity["failure"] = failure
    return {"activity": activity}


@pytest.fixture
def mock_post(monkeypatch):
    """Return a function that queues responses for requests.post."""
    calls: List[Dict[str, Any]] = []
    queue: List[Dict[str, Any]] = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append({"url": url, "data": data})
        return FakeResponse(queue.pop(0))

    monkeypatch.setattr(client_module.requests, "post", fake_post)

    def enqueue(*payloads: Dict[str, Any]) -> List[Dict[str, Any]]:
        queue.extend(payloads)
        return calls

    return enqueue


@pytest.fixture
def client() -> TurnkeyClient:
    """Override the live-credential client fixture from conftest.py."""
    return TurnkeyClient(
        base_url="https://api.example.invalid",
        stamper=StubStamper(),  # type: ignore[arg-type]
        organization_id=ORG_ID,
        polling_interval_ms=0,
        max_polling_retries=2,
    )


def create_wallet(client: TurnkeyClient):
    return client.create_wallet(CreateWalletBody(walletName="w", accounts=[]))


def test_completed_activity_unpacks_result(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_COMPLETED",
            result={"createWalletResult": {"walletId": "w-1", "addresses": ["0xabc"]}},
        )
    )

    response = create_wallet(client)

    assert response.walletId == "w-1"
    assert response.addresses == ["0xabc"]
    assert response.activity.id == ACTIVITY_ID


def test_failed_activity_raises_with_failure_text(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_FAILED",
            failure={"code": 7, "message": "policy denied"},
        )
    )

    with pytest.raises(TurnkeyActivityError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert type(err) is TurnkeyActivityError
    assert not isinstance(err, ValidationError)
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_FAILED"
    assert err.activity_type == "ACTIVITY_TYPE_CREATE_WALLET"
    assert err.failure == "policy denied"
    assert err.code == TurnkeyErrorCodes.ACTIVITY_FAILED
    assert "policy denied" in str(err)
    assert ACTIVITY_ID in str(err)


def test_rejected_activity_raises(client, mock_post):
    mock_post(activity_payload("ACTIVITY_STATUS_REJECTED"))

    with pytest.raises(TurnkeyActivityError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert type(err) is TurnkeyActivityError
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_REJECTED"
    assert "rejected" in str(err)


def test_consensus_needed_raises_subclass(client, mock_post):
    mock_post(activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"))

    with pytest.raises(TurnkeyActivityConsensusNeededError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert isinstance(err, TurnkeyActivityError)
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_CONSENSUS_NEEDED"
    assert err.code == TurnkeyErrorCodes.ACTIVITY_CONSENSUS_NEEDED


def test_polling_timeout_raises_with_last_status(client, mock_post):
    calls = mock_post(
        activity_payload("ACTIVITY_STATUS_CREATED"),
        activity_payload("ACTIVITY_STATUS_PENDING"),
        activity_payload("ACTIVITY_STATUS_PENDING"),
    )

    with pytest.raises(TurnkeyActivityError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert type(err) is TurnkeyActivityError
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_PENDING"
    # One submit plus max_polling_retries polls
    assert len(calls) == 3


def test_completed_activity_without_result_key_raises(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_COMPLETED",
            result={"createPolicyResult": {"policyId": "p-1"}},
        )
    )

    with pytest.raises(TurnkeyActivityError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert err.code == TurnkeyErrorCodes.ACTIVITY_RESULT_MISSING
    assert err.activity_status == "ACTIVITY_STATUS_COMPLETED"
    assert "createWalletResult" in str(err)


def signed_activity_request() -> SignedRequest:
    return SignedRequest(
        url="https://api.example.invalid/public/v1/submit/create_sub_organization",
        body="{}",
        stamp=TStamp(stamp_header_name="X-Stamp", stamp_header_value="stub"),
        type=RequestType.ACTIVITY,
    )


def test_generic_path_unpacks_versioned_result_key(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_COMPLETED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            result={
                "createSubOrganizationResultV7": {
                    "subOrganizationId": "sub-1",
                    "rootUserIds": ["u-1"],
                }
            },
        )
    )

    response = client.send_signed_request(
        signed_activity_request(), CreateSubOrganizationResponse
    )

    assert response.subOrganizationId == "sub-1"
    assert response.rootUserIds == ["u-1"]


def test_generic_path_raises_on_failed_activity(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_FAILED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            failure={"message": "quota exceeded"},
        )
    )

    with pytest.raises(TurnkeyActivityError) as exc_info:
        client.send_signed_request(signed_activity_request())

    assert exc_info.value.failure == "quota exceeded"
    assert exc_info.value.activity_id == ACTIVITY_ID
