import json
from base64 import urlsafe_b64encode
from unittest.mock import Mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
from turnkey_http import (
    TurnkeyClient,
    build_strict_otp_login_request,
    build_strict_otp_signup_request,
)
from turnkey_sdk_types import (
    v1LoginUsage,
    v1RootUserParamsV5,
    v1TokenUsage,
    v1UsageType,
    v1WalletParams,
)


def _client_stamper():
    private_key = ec.derive_private_key(1, ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    )
    return ApiKeyStamper(
        ApiKeyStamperConfig(
            api_public_key=public_key.hex(),
            api_private_key="01",
        )
    )


def _verification_token(public_key):
    claims = json.dumps(
        {"id": "token-id", "public_key": public_key}, separators=(",", ":")
    ).encode()
    payload = urlsafe_b64encode(claims).decode().rstrip("=")
    return f"header.{payload}.signature"


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
    assert len(body.clientSignature.signature) == 128


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


def test_strict_signup_uses_v5_root_users_and_binds_all_request_fields():
    stamper = _client_stamper()
    verification_token = _verification_token(stamper.api_public_key)
    root_users = [
        v1RootUserParamsV5(
            userName="Alice",
            userEmail="alice@example.com",
            apiKeys=[],
            authenticators=[],
            oauthProviders=[],
        ),
        v1RootUserParamsV5(
            userName="Bob",
            userPhoneNumber="+13214567890",
            apiKeys=[],
            authenticators=[],
            oauthProviders=[],
        ),
    ]
    wallet = v1WalletParams(walletName="Primary wallet", accounts=[])

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
    )

    assert ": " not in body.clientSignature.message
    assert ", " not in body.clientSignature.message
    signed = json.loads(body.clientSignature.message)
    assert signed["type"] == "USAGE_TYPE_SIGNUP"
    assert signed["tokenId"] == "token-id"
    signed_signup = signed["signupV3"]
    submitted = body.model_dump(by_alias=True, exclude_none=True)
    assert submitted["organizationId"] == signed_signup["parentOrganizationId"]
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
