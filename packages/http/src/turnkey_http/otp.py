"""Strict OTP login and signup request builders."""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from typing import Any, Dict, List, Optional, Tuple

from turnkey_api_key_stamper import ApiKeyStamper, SignatureFormat
from turnkey_sdk_types import (
    CreateSubOrganizationBody,
    OtpLoginBody,
    v1ClientSignature,
    v1ClientSignatureScheme,
    v1LoginUsageV2,
    v1RootUserParamsV5,
    v1SignupUsageV3,
    v1TokenUsage,
    v1UsageType,
    v1WalletParams,
)

__all__ = [
    "build_strict_otp_login_request",
    "build_strict_otp_signup_request",
]


def _verification_token_claims(verification_token: str) -> Tuple[str, str]:
    """Return the token ID and bound public key from a verification JWT."""
    try:
        payload = verification_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims: Dict[str, Any] = json.loads(urlsafe_b64decode(payload).decode())
        token_id = claims["id"]
        public_key = claims["public_key"]
    except (IndexError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(
            "Invalid verification token: expected id and public_key claims"
        ) from exc

    if not isinstance(token_id, str) or not isinstance(public_key, str):
        raise ValueError(  # noqa: TRY004
            "Invalid verification token: id and public_key must be strings"
        )

    return token_id, public_key


def _client_signature(
    client_stamper: ApiKeyStamper,
    verification_token: str,
    usage: v1TokenUsage,
) -> v1ClientSignature:
    token_id, verification_public_key = _verification_token_claims(verification_token)
    if usage.tokenId != token_id:
        raise ValueError("Token usage does not match the verification token")
    if client_stamper.api_public_key != verification_public_key:
        raise ValueError(
            "Client stamper public key does not match the verification token"
        )

    message = usage.model_dump_json(by_alias=True, exclude_none=True)
    return v1ClientSignature(
        publicKey=verification_public_key,
        scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
        message=message,
        signature=client_stamper.sign(message, SignatureFormat.RAW),
    )


def build_strict_otp_login_request(
    client_stamper: ApiKeyStamper,
    verification_token: str,
    organization_id: str,
    public_key: str,
    *,
    invalidate_existing: Optional[bool] = None,
    expiration_seconds: Optional[str] = None,
    session_profile_id: Optional[str] = None,
    timestamp_ms: Optional[str] = None,
) -> OtpLoginBody:
    """Build an OTP Login V2 body and bind its complete semantics to a signature.

    ``client_stamper`` must contain the key pair bound into ``verification_token``.
    ``public_key`` is the session public key submitted by the login request.
    """
    token_id, _ = _verification_token_claims(verification_token)
    login_usage = v1LoginUsageV2(
        organizationId=organization_id,
        publicKey=public_key,
        invalidateExisting=invalidate_existing,
        expirationSeconds=expiration_seconds,
        sessionProfileId=session_profile_id,
    )
    usage = v1TokenUsage(
        type=v1UsageType.USAGE_TYPE_LOGIN,
        tokenId=token_id,
        loginV2=login_usage,
    )
    client_signature = _client_signature(client_stamper, verification_token, usage)

    return OtpLoginBody(
        timestampMs=timestamp_ms,
        organizationId=login_usage.organizationId,
        verificationToken=verification_token,
        publicKey=login_usage.publicKey,
        clientSignature=client_signature,
        invalidateExisting=login_usage.invalidateExisting,
        expirationSeconds=login_usage.expirationSeconds,
        sessionProfileId=login_usage.sessionProfileId,
    )


def build_strict_otp_signup_request(
    client_stamper: ApiKeyStamper,
    verification_token: str,
    parent_organization_id: str,
    sub_organization_name: str,
    root_users: List[v1RootUserParamsV5],
    root_quorum_threshold: int,
    *,
    wallet: Optional[v1WalletParams] = None,
    disable_email_recovery: Optional[bool] = None,
    disable_email_auth: Optional[bool] = None,
    disable_sms_auth: Optional[bool] = None,
    disable_otp_email_auth: Optional[bool] = None,
    timestamp_ms: Optional[str] = None,
) -> CreateSubOrganizationBody:
    """Build a Create Sub Organization V8 body with strict Signup V3 binding."""
    token_id, _ = _verification_token_claims(verification_token)
    signup_usage = v1SignupUsageV3(
        parentOrganizationId=parent_organization_id,
        subOrganizationName=sub_organization_name,
        rootUsers=root_users,
        rootQuorumThreshold=root_quorum_threshold,
        wallet=wallet,
        disableEmailRecovery=disable_email_recovery,
        disableEmailAuth=disable_email_auth,
        disableSmsAuth=disable_sms_auth,
        disableOtpEmailAuth=disable_otp_email_auth,
    )
    usage = v1TokenUsage(
        type=v1UsageType.USAGE_TYPE_SIGNUP,
        tokenId=token_id,
        signupV3=signup_usage,
    )
    client_signature = _client_signature(client_stamper, verification_token, usage)

    return CreateSubOrganizationBody(
        timestampMs=timestamp_ms,
        organizationId=signup_usage.parentOrganizationId,
        subOrganizationName=signup_usage.subOrganizationName,
        rootUsers=signup_usage.rootUsers,
        rootQuorumThreshold=signup_usage.rootQuorumThreshold,
        wallet=signup_usage.wallet,
        disableEmailRecovery=signup_usage.disableEmailRecovery,
        disableEmailAuth=signup_usage.disableEmailAuth,
        disableSmsAuth=signup_usage.disableSmsAuth,
        disableOtpEmailAuth=signup_usage.disableOtpEmailAuth,
        verificationToken=verification_token,
        clientSignature=client_signature,
    )
