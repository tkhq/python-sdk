import json
from unittest.mock import patch

import pytest
from turnkey_api_key_stamper import TStamp
from turnkey_http.generated.client import TurnkeyClient
from turnkey_sdk_types import RequestType, SignedRequest, TurnkeyNetworkError

BASE_URL = "https://api.example.com"
ENDPOINT = "/public/v1/query/test"
STAMP_HEADER = "X-Stamp"
STAMP_VALUE = "stamp-value"


class StaticStamper:
    stamp_header_name = STAMP_HEADER

    def stamp(self, content):
        return TStamp(stamp_header_name=STAMP_HEADER, stamp_header_value=STAMP_VALUE)


class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.ok = status_code < 400
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)
        self.reason = ""

    def json(self):
        return self._payload


def redirect(status_code, location):
    return FakeResponse(status_code, headers={"Location": location})


@pytest.fixture
def transport_client():
    return TurnkeyClient(
        base_url=BASE_URL, stamper=StaticStamper(), organization_id="org-id"
    )


@pytest.fixture
def calls():
    return []


def fake_post(responses, calls):
    def post(url, headers=None, data=None, timeout=None, allow_redirects=True):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "data": data,
                "allow_redirects": allow_redirects,
            }
        )
        return responses.pop(0)

    return post


def run_request(transport_client, responses, calls):
    with patch(
        "turnkey_http.generated.client.requests.post",
        new=fake_post(responses, calls),
    ):
        return transport_client._request(ENDPOINT, {"organizationId": "org-id"}, dict)


def run_signed_request(transport_client, responses, calls, url=BASE_URL + ENDPOINT):
    signed_request = SignedRequest(
        url=url,
        body='{"organizationId": "org-id"}',
        stamp=TStamp(stamp_header_name=STAMP_HEADER, stamp_header_value=STAMP_VALUE),
        type=RequestType.QUERY,
    )
    with patch(
        "turnkey_http.generated.client.requests.post",
        new=fake_post(responses, calls),
    ):
        return transport_client.send_signed_request(signed_request)


def test_request_disables_automatic_redirects(transport_client, calls):
    run_request(transport_client, [FakeResponse(200, payload={"result": "ok"})], calls)

    assert len(calls) == 1
    assert calls[0]["allow_redirects"] is False


@pytest.mark.parametrize("status_code", [307, 308])
def test_same_origin_redirect_is_followed(transport_client, calls, status_code):
    responses = [
        redirect(status_code, BASE_URL + "/public/v1/query/other"),
        FakeResponse(200, payload={"result": "ok"}),
    ]

    result = run_request(transport_client, responses, calls)

    assert result == {"result": "ok"}
    assert len(calls) == 2
    assert calls[1]["url"] == BASE_URL + "/public/v1/query/other"
    assert calls[1]["headers"][STAMP_HEADER] == STAMP_VALUE
    assert calls[1]["data"] == calls[0]["data"]
    assert calls[1]["allow_redirects"] is False


def test_relative_redirect_is_followed(transport_client, calls):
    responses = [
        redirect(307, "/public/v1/query/other"),
        FakeResponse(200, payload={"result": "ok"}),
    ]

    result = run_request(transport_client, responses, calls)

    assert result == {"result": "ok"}
    assert calls[1]["url"] == BASE_URL + "/public/v1/query/other"


def test_default_port_redirect_is_followed(transport_client, calls):
    responses = [
        redirect(307, "https://api.example.com:443" + ENDPOINT),
        FakeResponse(200, payload={"result": "ok"}),
    ]

    result = run_request(transport_client, responses, calls)

    assert result == {"result": "ok"}
    assert len(calls) == 2


@pytest.mark.parametrize("status_code", [307, 308])
def test_other_host_redirect_is_not_followed(transport_client, calls, status_code):
    responses = [redirect(status_code, "https://other.example.com" + ENDPOINT)]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 1


def test_scheme_change_redirect_is_not_followed(transport_client, calls):
    responses = [redirect(307, "http://api.example.com" + ENDPOINT)]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 1


def test_port_change_redirect_is_not_followed(transport_client, calls):
    responses = [redirect(307, "https://api.example.com:8443" + ENDPOINT)]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 1


def test_redirect_chain_to_other_host_is_not_followed(transport_client, calls):
    responses = [
        redirect(307, BASE_URL + "/public/v1/query/hop"),
        redirect(308, "https://other.example.com" + ENDPOINT),
    ]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 2
    assert all(call["url"].startswith(BASE_URL + "/") for call in calls)


@pytest.mark.parametrize("status_code", [301, 302, 303])
def test_other_redirect_statuses_are_not_followed(transport_client, calls, status_code):
    responses = [redirect(status_code, BASE_URL + "/public/v1/query/other")]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 1


def test_redirect_without_location_is_not_followed(transport_client, calls):
    responses = [FakeResponse(307)]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 1


def test_redirect_limit_is_enforced(transport_client, calls):
    responses = [redirect(307, BASE_URL + ENDPOINT) for _ in range(6)]

    with pytest.raises(TurnkeyNetworkError):
        run_request(transport_client, responses, calls)

    assert len(calls) == 5


def test_send_signed_request_same_origin_redirect_is_followed(transport_client, calls):
    responses = [
        redirect(307, BASE_URL + "/public/v1/query/other"),
        FakeResponse(200, payload={"result": "ok"}),
    ]

    result = run_signed_request(transport_client, responses, calls)

    assert result == {"result": "ok"}
    assert len(calls) == 2
    assert calls[1]["url"] == BASE_URL + "/public/v1/query/other"
    assert calls[1]["headers"][STAMP_HEADER] == STAMP_VALUE
    assert calls[1]["data"] == calls[0]["data"]


@pytest.mark.parametrize("status_code", [307, 308])
def test_send_signed_request_other_host_redirect_is_not_followed(
    transport_client, calls, status_code
):
    responses = [redirect(status_code, "https://other.example.com" + ENDPOINT)]

    with pytest.raises(TurnkeyNetworkError):
        run_signed_request(transport_client, responses, calls)

    assert len(calls) == 1
