import json
from base64 import urlsafe_b64encode
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from turnkey_api_key_stamper import TStamp
from turnkey_http import (
    ClientSignaturePayload,
    TurnkeyClient,
    build_strict_otp_login_request,
    build_strict_otp_signup_request,
    get_client_signature_message_for_login_v2,
    get_client_signature_message_for_signup_v3,
)
from turnkey_sdk_types import (
    CreateSubOrganizationBody,
    v1AddressFormat,
    v1ApiKeyCurve,
    v1ApiKeyParamsV2,
    v1ClientSignature,
    v1ClientSignatureScheme,
    v1Curve,
    v1LoginUsage,
    v1LoginUsageV2,
    v1OauthProviderParamsV2,
    v1OidcClaims,
    v1PathFormat,
    v1RootUserParamsV4,
    v1RootUserParamsV5,
    v1SignupUsageV3,
    v1TokenUsage,
    v1UsageType,
    v1WalletAccountParams,
    v1WalletParams,
)

VERIFICATION_PUBLIC_KEY = "verification-public-key"


def _token_with_claims(claims):
    payload = (
        urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


def _verification_token(public_key=VERIFICATION_PUBLIC_KEY, token_id="token-id"):
    return _token_with_claims({"id": token_id, "public_key": public_key})


class FakeExternalSigner:
    def __init__(self):
        self.messages = []

    def sign(self, message):
        self.messages.append(message)
        return "ab" * 64


def _client_signature(payload, signer):
    return v1ClientSignature(
        publicKey=payload.public_key,
        scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
        message=payload.message,
        signature=signer.sign(payload.message),
    )


def _request_stamper():
    stamper = Mock()
    stamper.stamp.return_value = TStamp(
        stamp_header_name="X-Stamp",
        stamp_header_value="request-stamp",
    )
    return stamper


def test_login_message_is_exact_compact_camel_case_and_immutable():
    login_usage = v1LoginUsageV2(
        organizationId="organization-id",
        publicKey="session-public-key",
        invalidateExisting=False,
        expirationSeconds="3600",
        sessionProfileId="session-profile-id",
    )

    payload = get_client_signature_message_for_login_v2(
        _verification_token(),
        login_usage,
    )

    assert payload == ClientSignaturePayload(
        message=(
            '{"type":"USAGE_TYPE_LOGIN","tokenId":"token-id","loginV2":'
            '{"organizationId":"organization-id","publicKey":"session-public-key",'
            '"invalidateExisting":false,"expirationSeconds":"3600",'
            '"sessionProfileId":"session-profile-id"}}'
        ),
        token_id="token-id",
        public_key=VERIFICATION_PUBLIC_KEY,
    )
    with pytest.raises(FrozenInstanceError):
        payload.message = "different"  # type: ignore[misc]


def test_login_message_omits_none_but_retains_false():
    payload = get_client_signature_message_for_login_v2(
        _verification_token(),
        v1LoginUsageV2(
            organizationId="organization-id",
            publicKey="session-public-key",
            invalidateExisting=False,
        ),
    )

    assert json.loads(payload.message)["loginV2"] == {
        "organizationId": "organization-id",
        "publicKey": "session-public-key",
        "invalidateExisting": False,
    }


@pytest.mark.parametrize(
    "verification_token",
    [
        "missing-payload",
        _token_with_claims({}),
        _token_with_claims({"id": 123, "public_key": "public-key"}),
        _token_with_claims({"id": "token-id", "public_key": 123}),
        _token_with_claims({"id": "", "public_key": "public-key"}),
        _token_with_claims({"id": "token-id", "public_key": ""}),
    ],
)
def test_message_utilities_reject_malformed_verification_tokens(verification_token):
    with pytest.raises(ValueError, match="Invalid verification token"):
        get_client_signature_message_for_login_v2(
            verification_token,
            v1LoginUsageV2(
                organizationId="organization-id",
                publicKey="session-public-key",
            ),
        )


@pytest.mark.parametrize("mismatch", ["public_key", "message"])
def test_login_request_rejects_client_signature_binding_mismatch(mismatch):
    verification_token = _verification_token()
    login_usage = v1LoginUsageV2(
        organizationId="organization-id",
        publicKey="session-public-key",
    )
    payload = get_client_signature_message_for_login_v2(
        verification_token,
        login_usage,
    )
    public_key = payload.public_key
    message = payload.message
    if mismatch == "public_key":
        public_key = "different-token-public-key"
    else:
        message = message.replace("session-public-key", "different-session-key")
    client_signature = v1ClientSignature(
        publicKey=public_key,
        scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
        message=message,
        signature="ab" * 64,
    )

    with pytest.raises(ValueError, match="does not match"):
        build_strict_otp_login_request(
            verification_token,
            login_usage,
            client_signature,
        )


def test_login_request_rejects_signature_from_different_verification_token_key():
    login_usage = v1LoginUsageV2(
        organizationId="organization-id",
        publicKey="session-public-key",
    )
    first_token = _verification_token("first-token-public-key")
    first_payload = get_client_signature_message_for_login_v2(
        first_token,
        login_usage,
    )
    client_signature = _client_signature(first_payload, FakeExternalSigner())

    with pytest.raises(ValueError, match="public key does not match"):
        build_strict_otp_login_request(
            _verification_token("second-token-public-key"),
            login_usage,
            client_signature,
        )


def test_login_request_rejects_non_raw_client_signature():
    verification_token = _verification_token()
    login_usage = v1LoginUsageV2(
        organizationId="organization-id",
        publicKey="session-public-key",
    )
    payload = get_client_signature_message_for_login_v2(
        verification_token,
        login_usage,
    )
    client_signature = v1ClientSignature(
        publicKey=payload.public_key,
        scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
        message=payload.message,
        signature="not-a-raw-signature",
    )

    with pytest.raises(ValueError, match="raw P-256"):
        build_strict_otp_login_request(
            verification_token,
            login_usage,
            client_signature,
        )


def test_login_request_uses_fake_external_signer_and_matches_signed_usage():
    verification_token = _verification_token()
    login_usage = v1LoginUsageV2(
        organizationId="organization-id",
        publicKey="session-public-key",
        invalidateExisting=False,
        expirationSeconds="3600",
        sessionProfileId="session-profile-id",
    )
    payload = get_client_signature_message_for_login_v2(
        verification_token,
        login_usage,
    )
    signer = FakeExternalSigner()
    client_signature = _client_signature(payload, signer)

    body = build_strict_otp_login_request(
        verification_token,
        login_usage,
        client_signature,
        timestamp_ms="1234",
    )

    assert signer.messages == [payload.message]
    assert body.clientSignature.signature == "ab" * 64
    signed = json.loads(payload.message)["loginV2"]
    assert body.organizationId == signed["organizationId"]
    assert body.publicKey == signed["publicKey"]
    assert body.invalidateExisting is signed["invalidateExisting"]
    assert body.expirationSeconds == signed["expirationSeconds"]
    assert body.sessionProfileId == signed["sessionProfileId"]


def test_signup_message_and_generated_submission_match_typed_usage():
    verification_token = _verification_token()
    root_users = [
        v1RootUserParamsV5(
            userName="Alice",
            userEmail="alice@example.com",
            apiKeys=[
                v1ApiKeyParamsV2(
                    apiKeyName="Alice client key",
                    publicKey="api-public-key",
                    curveType=v1ApiKeyCurve.API_KEY_CURVE_P256,
                    expirationSeconds="86400",
                )
            ],
            authenticators=[],
            oauthProviders=[
                v1OauthProviderParamsV2(
                    providerName="Example OIDC",
                    oidcClaims=v1OidcClaims(
                        iss="https://issuer.example.com",
                        sub="alice-subject",
                        aud="turnkey-python-test",
                    ),
                )
            ],
        ),
        v1RootUserParamsV5(
            userName="Bob",
            userPhoneNumber="+13214567890",
            apiKeys=[],
            authenticators=[],
            oauthProviders=[],
        ),
    ]
    wallet = v1WalletParams(
        walletName="Primary wallet",
        accounts=[
            v1WalletAccountParams(
                curve=v1Curve.CURVE_SECP256K1,
                pathFormat=v1PathFormat.PATH_FORMAT_BIP32,
                path="m/44'/60'/0'/0/0",
                addressFormat=v1AddressFormat.ADDRESS_FORMAT_ETHEREUM,
            )
        ],
        mnemonicLength=24,
    )
    signup_usage = v1SignupUsageV3(
        parentOrganizationId="parent-organization-id",
        subOrganizationName="Strict sub-organization",
        rootUsers=root_users,
        rootQuorumThreshold=2,
        wallet=wallet,
        disableEmailRecovery=False,
        disableEmailAuth=True,
        disableSmsAuth=False,
        disableOtpEmailAuth=True,
    )
    payload = get_client_signature_message_for_signup_v3(
        verification_token,
        signup_usage,
    )
    assert payload.message == json.dumps(
        {
            "type": "USAGE_TYPE_SIGNUP",
            "tokenId": "token-id",
            "signupV3": signup_usage.model_dump(by_alias=True, exclude_none=True),
        },
        separators=(",", ":"),
    )
    signer = FakeExternalSigner()
    client_signature = _client_signature(payload, signer)

    body = build_strict_otp_signup_request(
        verification_token,
        signup_usage,
        client_signature,
        timestamp_ms="1234",
    )
    client = TurnkeyClient(
        base_url="https://api.turnkey.com",
        stamper=_request_stamper(),
        organization_id="default-organization-id",
    )
    submission = json.loads(client.stamp_create_sub_organization(body).body)

    assert signer.messages == [payload.message]
    assert ": " not in payload.message
    assert ", " not in payload.message
    signed = json.loads(payload.message)
    assert signed["type"] == "USAGE_TYPE_SIGNUP"
    assert signed["tokenId"] == "token-id"
    signed_signup = signed["signupV3"]
    submitted = submission["parameters"]
    assert submission["timestampMs"] == "1234"
    assert submission["organizationId"] == signed_signup["parentOrganizationId"]
    assert submitted["verificationToken"] == verification_token
    assert submitted["clientSignature"] == client_signature.model_dump(
        by_alias=True, exclude_none=True
    )
    assert submitted["subOrganizationName"] == signed_signup["subOrganizationName"]
    assert submitted["rootUsers"] == signed_signup["rootUsers"]
    assert submitted["rootQuorumThreshold"] == signed_signup["rootQuorumThreshold"]
    assert submitted["wallet"] == signed_signup["wallet"]
    assert submitted["disableEmailRecovery"] is signed_signup["disableEmailRecovery"]
    assert submitted["disableEmailAuth"] is signed_signup["disableEmailAuth"]
    assert submitted["disableSmsAuth"] is signed_signup["disableSmsAuth"]
    assert submitted["disableOtpEmailAuth"] is signed_signup["disableOtpEmailAuth"]
    assert "userPhoneNumber" not in signed_signup["rootUsers"][0]
    assert "userEmail" not in signed_signup["rootUsers"][1]
    assert submitted["rootUsers"][0]["apiKeys"][0] == {
        "apiKeyName": "Alice client key",
        "publicKey": "api-public-key",
        "curveType": "API_KEY_CURVE_P256",
        "expirationSeconds": "86400",
    }
    assert submitted["rootUsers"][0]["oauthProviders"][0]["oidcClaims"] == {
        "iss": "https://issuer.example.com",
        "sub": "alice-subject",
        "aud": "turnkey-python-test",
    }
    assert submitted["wallet"]["accounts"][0] == {
        "curve": "CURVE_SECP256K1",
        "pathFormat": "PATH_FORMAT_BIP32",
        "path": "m/44'/60'/0'/0/0",
        "addressFormat": "ADDRESS_FORMAT_ETHEREUM",
    }


def test_create_sub_organization_body_rejects_v4_root_user_models():
    root_user_v4 = v1RootUserParamsV4(
        userName="Alice",
        apiKeys=[],
        authenticators=[],
        oauthProviders=[],
    )

    with pytest.raises(ValidationError, match="v1RootUserParamsV5"):
        CreateSubOrganizationBody(
            subOrganizationName="Strict sub-organization",
            rootUsers=[root_user_v4],
            rootQuorumThreshold=1,
        )


def test_unversioned_create_sub_organization_uses_v8_activity_and_result():
    verification_token = _verification_token()
    signup_usage = v1SignupUsageV3(
        parentOrganizationId="parent-organization-id",
        subOrganizationName="Strict sub-organization",
        rootUsers=[
            v1RootUserParamsV5(
                userName="Alice",
                apiKeys=[],
                authenticators=[],
                oauthProviders=[],
            )
        ],
        rootQuorumThreshold=1,
    )
    payload = get_client_signature_message_for_signup_v3(
        verification_token,
        signup_usage,
    )
    body = build_strict_otp_signup_request(
        verification_token,
        signup_usage,
        _client_signature(payload, FakeExternalSigner()),
        timestamp_ms="1234",
    )
    client = TurnkeyClient(
        base_url="https://api.turnkey.com",
        stamper=_request_stamper(),
        organization_id="default-organization-id",
    )

    activity = Mock()
    client._activity = activity
    client.create_sub_organization(body)
    _, activity_body, result_key, _ = activity.call_args.args

    assert activity_body["type"] == "ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V8"
    assert result_key == "createSubOrganizationResultV8"


def test_legacy_token_usage_variants_remain_usable():
    usage = v1TokenUsage(
        type=v1UsageType.USAGE_TYPE_LOGIN,
        tokenId="legacy-token-id",
        login=v1LoginUsage(publicKey="legacy-public-key"),
    )

    assert usage.model_dump(by_alias=True, exclude_none=True) == {
        "type": v1UsageType.USAGE_TYPE_LOGIN,
        "tokenId": "legacy-token-id",
        "login": {"publicKey": "legacy-public-key"},
    }
