import json
from base64 import urlsafe_b64encode
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from pydantic import ValidationError
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
from turnkey_http import (
    TurnkeyClient,
    build_strict_otp_login_request,
    build_strict_otp_signup_request,
)
from turnkey_sdk_types import (
    CreateSubOrganizationBody,
    v1AddressFormat,
    v1ApiKeyCurve,
    v1ApiKeyParamsV2,
    v1Curve,
    v1LoginUsage,
    v1OauthProviderParamsV2,
    v1OidcClaims,
    v1PathFormat,
    v1RootUserParamsV4,
    v1RootUserParamsV5,
    v1TokenUsage,
    v1UsageType,
    v1WalletAccountParams,
    v1WalletParams,
)


def _client_stamper(private_value=1):
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    )
    return ApiKeyStamper(
        ApiKeyStamperConfig(
            api_public_key=public_key.hex(),
            api_private_key=f"{private_value:02x}",
        )
    )


def _token_with_claims(claims):
    payload = (
        urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


def _verification_token(public_key, token_id="token-id"):
    return _token_with_claims({"id": token_id, "public_key": public_key})


def _assert_client_signature_verifies(client_signature):
    signature = bytes.fromhex(client_signature.signature)
    assert len(signature) == 64
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(client_signature.publicKey)
    )
    public_key.verify(
        encode_dss_signature(r, s),
        client_signature.message.encode(),
        ec.ECDSA(hashes.SHA256()),
    )


def test_strict_login_uses_exact_compact_message_and_shared_values():
    stamper = _client_stamper()
    verification_token = _verification_token(stamper.api_public_key)

    body = build_strict_otp_login_request(
        stamper,
        verification_token,
        "organization-id",
        "session-public-key",
        invalidate_existing=False,
        expiration_seconds="3600",
        session_profile_id="session-profile-id",
    )

    expected_usage = {
        "type": "USAGE_TYPE_LOGIN",
        "tokenId": "token-id",
        "loginV2": {
            "organizationId": "organization-id",
            "publicKey": "session-public-key",
            "invalidateExisting": False,
            "expirationSeconds": "3600",
            "sessionProfileId": "session-profile-id",
        },
    }
    assert body.clientSignature.message == json.dumps(
        expected_usage, separators=(",", ":")
    )
    signed = json.loads(body.clientSignature.message)["loginV2"]
    assert body.organizationId == signed["organizationId"]
    assert body.publicKey == signed["publicKey"]
    assert body.invalidateExisting is signed["invalidateExisting"]
    assert body.expirationSeconds == signed["expirationSeconds"]
    assert body.sessionProfileId == signed["sessionProfileId"]
    assert body.clientSignature.publicKey == stamper.api_public_key
    _assert_client_signature_verifies(body.clientSignature)


def test_strict_login_omits_none_but_retains_false():
    stamper = _client_stamper()
    body = build_strict_otp_login_request(
        stamper,
        _verification_token(stamper.api_public_key),
        "organization-id",
        "session-public-key",
        invalidate_existing=False,
    )

    assert json.loads(body.clientSignature.message)["loginV2"] == {
        "organizationId": "organization-id",
        "publicKey": "session-public-key",
        "invalidateExisting": False,
    }


def test_strict_login_rejects_stamper_not_bound_to_verification_token():
    token_stamper = _client_stamper(1)
    signing_stamper = _client_stamper(2)

    with pytest.raises(ValueError, match="does not match"):
        build_strict_otp_login_request(
            signing_stamper,
            _verification_token(token_stamper.api_public_key),
            "organization-id",
            "session-public-key",
        )


@pytest.mark.parametrize(
    "verification_token",
    [
        "missing-payload",
        _token_with_claims({}),
        _token_with_claims({"id": 123, "public_key": "public-key"}),
        _token_with_claims({"id": "token-id", "public_key": 123}),
    ],
)
def test_strict_login_rejects_malformed_verification_token(verification_token):
    with pytest.raises(ValueError, match="Invalid verification token"):
        build_strict_otp_login_request(
            _client_stamper(),
            verification_token,
            "organization-id",
            "session-public-key",
        )


def test_strict_signup_uses_v5_root_users_and_binds_submission_payload():
    stamper = _client_stamper()
    verification_token = _verification_token(stamper.api_public_key)
    root_users = [
        v1RootUserParamsV5(
            userName="Alice",
            userEmail="alice@example.com",
            apiKeys=[
                v1ApiKeyParamsV2(
                    apiKeyName="Alice client key",
                    publicKey=stamper.api_public_key,
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

    body = build_strict_otp_signup_request(
        stamper,
        verification_token,
        "parent-organization-id",
        "Strict sub-organization",
        root_users,
        2,
        wallet=wallet,
        disable_email_recovery=False,
        disable_email_auth=True,
        disable_sms_auth=False,
        disable_otp_email_auth=True,
        timestamp_ms="1234",
    )
    client = TurnkeyClient(
        base_url="https://api.turnkey.com",
        stamper=stamper,
        organization_id="default-organization-id",
    )
    submission = json.loads(client.stamp_create_sub_organization(body).body)

    assert ": " not in body.clientSignature.message
    assert ", " not in body.clientSignature.message
    signed = json.loads(body.clientSignature.message)
    assert signed["type"] == "USAGE_TYPE_SIGNUP"
    assert signed["tokenId"] == "token-id"
    signed_signup = signed["signupV3"]
    submitted = submission["parameters"]
    assert submission["timestampMs"] == "1234"
    assert submission["organizationId"] == signed_signup["parentOrganizationId"]
    assert submitted["verificationToken"] == verification_token
    assert submitted["clientSignature"] == body.clientSignature.model_dump(
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
        "publicKey": stamper.api_public_key,
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
    _assert_client_signature_verifies(body.clientSignature)


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


def test_unversioned_create_sub_organization_stamps_v8():
    stamper = _client_stamper()
    body = build_strict_otp_signup_request(
        stamper,
        _verification_token(stamper.api_public_key),
        "parent-organization-id",
        "Strict sub-organization",
        [
            v1RootUserParamsV5(
                userName="Alice",
                apiKeys=[],
                authenticators=[],
                oauthProviders=[],
            )
        ],
        1,
        timestamp_ms="1234",
    )
    client = TurnkeyClient(
        base_url="https://api.turnkey.com",
        stamper=stamper,
        organization_id="default-organization-id",
    )

    activity = Mock()
    client._activity = activity
    client.create_sub_organization(body)
    _, activity_body, result_key, _ = activity.call_args.args

    assert activity_body["type"] == "ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V8"
    assert result_key == "createSubOrganizationResultV8"

    signed_request = client.stamp_create_sub_organization(body)
    submitted = json.loads(signed_request.body)
    assert submitted["type"] == "ACTIVITY_TYPE_CREATE_SUB_ORGANIZATION_V8"
    assert submitted["organizationId"] == "parent-organization-id"
    assert submitted["parameters"]["rootUsers"][0]["userName"] == "Alice"


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
