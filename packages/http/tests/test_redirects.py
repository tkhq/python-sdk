import json
from unittest.mock import patch

import pytest
from turnkey_api_key_stamper import TStamp
from turnkey_http.generated.client import TurnkeyClient
from turnkey_sdk_types import RequestType, SignedRequest, TurnkeyNetworkError

BASE_URL = "https://api.example.com"
ENDPOINT = "/public/v1/query/test"
STAMP = TStamp(stamp_header_name="X-Stamp", stamp_header_value="stamp-value")


class StaticStamper:
    def stamp(self, content):
        return STAMP


class FakeResponse:
    def __init__(self, status_code, location=None, payload=None):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.ok = status_code < 400
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.reason = ""

    def json(self):
        return self._payload


@pytest.fixture
def client():
    return TurnkeyClient(BASE_URL, StaticStamper(), "org-id")


@pytest.fixture
def calls():
    return []


def send(client, calls, responses, signed=False):
    def post(url, headers, data, timeout, allow_redirects):
        calls.append((url, headers, data, allow_redirects))
        return responses.pop(0)

    with patch("turnkey_http.generated.client.requests.post", new=post):
        if signed:
            request = SignedRequest(
                BASE_URL + ENDPOINT,
                '{"organizationId": "org-id"}',
                STAMP,
                RequestType.QUERY,
            )
            return client.send_signed_request(request)
        return client._request(ENDPOINT, {"organizationId": "org-id"}, dict)


@pytest.mark.parametrize(
    "signed,status_code,location",
    [
        (False, 307, "https://other.example.com" + ENDPOINT),
        (True, 308, "http://api.example.com" + ENDPOINT),
    ],
)
def test_cross_origin_redirect_is_not_followed(
    client, calls, signed, status_code, location
):
    responses = [FakeResponse(status_code, location)]

    with pytest.raises(TurnkeyNetworkError):
        send(client, calls, responses, signed)

    assert len(calls) == 1
    assert calls[0][3] is False


def test_same_origin_redirect_preserves_request(client, calls):
    responses = [
        FakeResponse(307, BASE_URL + "/public/v1/query/other"),
        FakeResponse(200, payload={"result": "ok"}),
    ]

    assert send(client, calls, responses) == {"result": "ok"}
    assert calls[1][0] == BASE_URL + "/public/v1/query/other"
    assert calls[1][1:] == calls[0][1:]


def test_redirect_chain_stays_on_original_origin(client, calls):
    responses = [
        FakeResponse(307, BASE_URL + "/public/v1/query/hop"),
        FakeResponse(308, "https://other.example.com" + ENDPOINT),
    ]

    with pytest.raises(TurnkeyNetworkError):
        send(client, calls, responses)

    assert [call[0] for call in calls] == [
        BASE_URL + ENDPOINT,
        BASE_URL + "/public/v1/query/hop",
    ]
