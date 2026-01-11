import requests
from typing import Any, TypeVar, Callable, overload

from .version import VERSION
from turnkey_sdk_types import TurnkeyNetworkError, TurnkeyErrorCodes
from .generated.client import TSignedRequest

T = TypeVar("T")


@overload
def send_signed_request(
    signed_request: TSignedRequest, parser: Callable[[Any], T]
) -> T: ...


@overload
def send_signed_request(signed_request: TSignedRequest) -> Any: ...


def send_signed_request(
    signed_request: TSignedRequest, parser: Callable[[Any], T] | None = None
) -> Any:
    """
    Submits a signed request to Turnkey.

    You can pass in the SignedRequest returned by any of the SDK's
    stamping methods (stamp_stamp_login, stamp_get_policies, etc.).

    [param] signed_request: A SignedRequest object returned by a stamping method.
    [param] parser: Optional callable to convert the JSON payload to a typed value.
    [returns] The parsed JSON response from Turnkey (or typed via parser).
    [raises] TurnkeyNetworkError if the request fails.
    """

    headers = {
        "Content-Type": "application/json",
        "X-Client-Version": VERSION,
        signed_request.stamp.stamp_header_name: signed_request.stamp.stamp_header_value,
    }

    try:
        response = requests.post(
            signed_request.url,
            headers=headers,
            data=signed_request.body,
        )
    except requests.RequestException as exc:
        raise TurnkeyNetworkError(
            "Signed request failed",
            None,
            TurnkeyErrorCodes.NETWORK_ERROR,
            str(exc),
        ) from exc

    if not response.ok:
        raise TurnkeyNetworkError(
            "Signed request failed",
            response.status_code,
            TurnkeyErrorCodes.BAD_RESPONSE,
            response.text,
        )

    payload = response.json()
    return parser(payload) if parser is not None else payload
