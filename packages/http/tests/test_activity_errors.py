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
    TurnkeyActivityAuthenticatorsNeededError,
    TurnkeyActivityConsensusNeededError,
    TurnkeyActivityError,
    TurnkeyErrorCodes,
)
from turnkey_http.generated import client as client_module
from turnkey_http.generated.client import PollingConfig, TurnkeyClient

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


def completed_wallet_payload() -> Dict[str, Any]:
    return activity_payload(
        "ACTIVITY_STATUS_COMPLETED",
        result={"createWalletResult": {"walletId": "w-1", "addresses": ["0xabc"]}},
    )


def enable_mfa_polling(client: TurnkeyClient) -> None:
    client.mfa_polling = PollingConfig(interval_ms=1, timeout_ms=5000)


def enable_consensus_polling(client: TurnkeyClient) -> None:
    client.consensus_polling = PollingConfig(interval_ms=1, timeout_ms=5000)


def record_sleeps(monkeypatch) -> List[float]:
    sleeps: List[float] = []
    clock = {"now": 0.0}

    def monotonic() -> float:
        return clock["now"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(client_module.time, "monotonic", monotonic)
    monkeypatch.setattr(client_module.time, "sleep", sleep)
    return sleeps


def test_authenticators_needed_raises_when_mfa_polling_is_off(client, mock_post):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"))

    with pytest.raises(TurnkeyActivityAuthenticatorsNeededError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert isinstance(err, TurnkeyActivityError)
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"
    assert err.activity_type == "ACTIVITY_TYPE_CREATE_WALLET"
    assert err.code == TurnkeyErrorCodes.ACTIVITY_AUTHENTICATORS_NEEDED
    # Terminal status: one submit, no extra polls.
    assert len(calls) == 1


def test_mfa_polling_waits_then_unpacks_result(client, mock_post):
    calls = mock_post(
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        completed_wallet_payload(),
    )
    enable_mfa_polling(client)

    response = create_wallet(client)

    assert response.walletId == "w-1"
    # Submit, then two MFA polls.
    assert len(calls) == 3


def test_mfa_polling_timeout_raises(client, mock_post, monkeypatch):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"))
    clock = {"now": 0.0}

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(client_module.time, "monotonic", monotonic)
    monkeypatch.setattr(client_module.time, "sleep", sleep)
    client.mfa_polling = PollingConfig(interval_ms=1000, timeout_ms=1)

    with pytest.raises(TurnkeyActivityAuthenticatorsNeededError) as exc_info:
        create_wallet(client)

    assert exc_info.value.activity_id == ACTIVITY_ID
    # Timeout fires before the first MFA fetch.
    assert len(calls) == 1


def test_mfa_polling_requires_both_interval_and_timeout(client, mock_post):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"))
    client.mfa_polling = PollingConfig(interval_ms=1, timeout_ms=0)

    with pytest.raises(TurnkeyActivityAuthenticatorsNeededError):
        create_wallet(client)

    assert len(calls) == 1


def test_mfa_polling_failure_raises_activity_error(client, mock_post):
    mock_post(
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        activity_payload(
            "ACTIVITY_STATUS_FAILED",
            failure={"message": "policy denied"},
        ),
    )
    enable_mfa_polling(client)

    with pytest.raises(TurnkeyActivityError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert type(err) is TurnkeyActivityError
    assert err.activity_status == "ACTIVITY_STATUS_FAILED"
    assert err.failure == "policy denied"


def test_mfa_polling_resumes_activity_poll_when_pending(client, mock_post):
    calls = mock_post(
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_PENDING"),
        completed_wallet_payload(),
    )
    enable_mfa_polling(client)

    response = create_wallet(client)

    assert response.walletId == "w-1"
    assert len(calls) == 3


def test_consensus_needed_raises_subclass(client, mock_post):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"))

    with pytest.raises(TurnkeyActivityConsensusNeededError) as exc_info:
        create_wallet(client)

    err = exc_info.value
    assert isinstance(err, TurnkeyActivityError)
    assert err.activity_id == ACTIVITY_ID
    assert err.activity_status == "ACTIVITY_STATUS_CONSENSUS_NEEDED"
    assert err.code == TurnkeyErrorCodes.ACTIVITY_CONSENSUS_NEEDED
    assert len(calls) == 1


def test_consensus_polling_waits_then_unpacks_result(client, mock_post):
    calls = mock_post(
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
        completed_wallet_payload(),
    )
    enable_consensus_polling(client)

    response = create_wallet(client)

    assert response.walletId == "w-1"
    assert len(calls) == 3


def test_consensus_polling_timeout_raises(client, mock_post, monkeypatch):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"))
    record_sleeps(monkeypatch)
    client.consensus_polling = PollingConfig(interval_ms=1000, timeout_ms=1)

    with pytest.raises(TurnkeyActivityConsensusNeededError) as exc_info:
        create_wallet(client)

    assert exc_info.value.activity_id == ACTIVITY_ID
    assert len(calls) == 1


def test_consensus_polling_requires_both_interval_and_timeout(client, mock_post):
    calls = mock_post(activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"))
    client.consensus_polling = PollingConfig(interval_ms=1, timeout_ms=0)

    with pytest.raises(TurnkeyActivityConsensusNeededError):
        create_wallet(client)

    assert len(calls) == 1


def test_consensus_polling_uses_a_fixed_interval(client, mock_post, monkeypatch):
    mock_post(
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
        completed_wallet_payload(),
    )
    sleeps = record_sleeps(monkeypatch)
    client.consensus_polling = PollingConfig(interval_ms=1000, timeout_ms=10_000)

    create_wallet(client)

    assert sleeps == [1.0, 1.0]


def test_mfa_polling_backs_off(client, mock_post, monkeypatch):
    mock_post(
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        completed_wallet_payload(),
    )
    sleeps = record_sleeps(monkeypatch)
    client.mfa_polling = PollingConfig(interval_ms=1000, timeout_ms=10_000)

    create_wallet(client)

    assert sleeps == [1.0, 2.0]


def test_approval_polls_do_not_chain(client, mock_post):
    calls = mock_post(
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
    )
    enable_mfa_polling(client)
    enable_consensus_polling(client)

    with pytest.raises(TurnkeyActivityConsensusNeededError):
        create_wallet(client)

    assert len(calls) == 2

    mock_post(
        activity_payload("ACTIVITY_STATUS_CONSENSUS_NEEDED"),
        activity_payload("ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"),
    )

    with pytest.raises(TurnkeyActivityAuthenticatorsNeededError):
        create_wallet(client)

    assert len(calls) == 4


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


def test_generic_path_with_type_raises_on_failed_activity(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_FAILED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            failure={"message": "quota exceeded"},
        )
    )

    with pytest.raises(TurnkeyActivityError) as exc_info:
        client.send_signed_request(
            signed_activity_request(), CreateSubOrganizationResponse
        )

    assert exc_info.value.failure == "quota exceeded"
    assert exc_info.value.activity_id == ACTIVITY_ID


def test_raw_path_returns_failed_activity(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_FAILED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            failure={"code": 7, "message": "policy denied"},
        )
    )

    payload = client.send_signed_request(signed_activity_request())

    assert isinstance(payload, dict)
    assert payload["activity"]["id"] == ACTIVITY_ID
    assert payload["activity"]["status"] == "ACTIVITY_STATUS_FAILED"
    assert payload["activity"]["failure"]["message"] == "policy denied"


def test_raw_path_returns_authenticators_needed_activity(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
        )
    )

    payload = client.send_signed_request(signed_activity_request())

    assert isinstance(payload, dict)
    assert payload["activity"]["status"] == "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED"


def test_signed_request_mfa_polling_unpacks_result(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
        ),
        activity_payload(
            "ACTIVITY_STATUS_COMPLETED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            result={
                "createSubOrganizationResultV7": {
                    "subOrganizationId": "sub-1",
                    "rootUserIds": ["u-1"],
                }
            },
        ),
    )
    enable_mfa_polling(client)

    response = client.send_signed_request(
        signed_activity_request(), CreateSubOrganizationResponse
    )

    assert response.subOrganizationId == "sub-1"


def test_raw_path_returns_consensus_needed_activity(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_CONSENSUS_NEEDED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
        )
    )

    payload = client.send_signed_request(signed_activity_request())

    assert isinstance(payload, dict)
    assert payload["activity"]["id"] == ACTIVITY_ID
    assert payload["activity"]["status"] == "ACTIVITY_STATUS_CONSENSUS_NEEDED"


def test_raw_path_unpacks_versioned_result_key(client, mock_post):
    mock_post(
        activity_payload(
            "ACTIVITY_STATUS_COMPLETED",
            activity_type="ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V7",
            result={"createSubOrganizationResultV7": {"subOrganizationId": "sub-1"}},
        )
    )

    payload = client.send_signed_request(signed_activity_request())

    assert payload["subOrganizationId"] == "sub-1"
    assert payload["activity"]["status"] == "ACTIVITY_STATUS_COMPLETED"
