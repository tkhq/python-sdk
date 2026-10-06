"""Pure utilities for strict OTP client-signature messages and requests."""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from turnkey_sdk_types import (
    CreateSubOrganizationBody,
    OtpLoginBody,
    v1ClientSignature,
    v1ClientSignatureScheme,
    v1LoginUsageV2,
    v1SignupUsageV3,
    v1TokenUsage,
    v1UsageType,
)

__all__ = [
    "ClientSignaturePayload",
    "build_strict_otp_login_request",
    "build_strict_otp_signup_request",
    "get_client_signature_message_for_login_v2",
    "get_client_signature_message_for_signup_v3",
]


@dataclass(frozen=True)
class ClientSignaturePayload:
    """Message and verification-token claims needed by an external signer."""

    message: str
    token_id: str
    public_key: str


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
    if not token_id or not public_key:
        raise ValueError(
            "Invalid verification token: id and public_key must not be empty"
        )

    return token_id, public_key


def _client_signature_payload(
    token_id: str,
    public_key: str,
    usage: v1TokenUsage,
) -> ClientSignaturePayload:
    return ClientSignaturePayload(
        message=usage.model_dump_json(by_alias=True, exclude_none=True),
        token_id=token_id,
        public_key=public_key,
    )


def get_client_signature_message_for_login_v2(
    verification_token: str,
    login_usage: v1LoginUsageV2,
) -> ClientSignaturePayload:
    """Build the strict Login V2 message for a caller-controlled signer."""
    token_id, public_key = _verification_token_claims(verification_token)
    usage = v1TokenUsage(
        type=v1UsageType.USAGE_TYPE_LOGIN,
        tokenId=token_id,
        loginV2=login_usage,
    )
    return _client_signature_payload(token_id, public_key, usage)


def get_client_signature_message_for_signup_v3(
    verification_token: str,
    signup_usage: v1SignupUsageV3,
) -> ClientSignaturePayload:
    """Build the strict Signup V3 message for a caller-controlled signer."""
    token_id, public_key = _verification_token_claims(verification_token)
    usage = v1TokenUsage(
        type=v1UsageType.USAGE_TYPE_SIGNUP,
        tokenId=token_id,
        signupV3=signup_usage,
    )
    return _client_signature_payload(token_id, public_key, usage)


def _validate_client_signature(
    payload: ClientSignaturePayload,
    client_signature: v1ClientSignature,
) -> None:
    if (
        client_signature.scheme
        != v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256
    ):
        raise ValueError("Client signature must use the P-256 client-signature scheme")
    if client_signature.publicKey != payload.public_key:
        raise ValueError(
            "Client signature public key does not match the verification token"
        )
    if client_signature.message != payload.message:
        raise ValueError("Client signature message does not match the request usage")
    try:
        signature = bytes.fromhex(client_signature.signature)
    except ValueError as exc:
        raise ValueError("Client signature must be raw P-256 hexadecimal") from exc
    if len(client_signature.signature) != 128 or len(signature) != 64:
        raise ValueError("Client signature must be a 64-byte raw P-256 signature")


def build_strict_otp_login_request(
    verification_token: str,
    login_usage: v1LoginUsageV2,
    client_signature: v1ClientSignature,
    *,
    timestamp_ms: Optional[str] = None,
) -> OtpLoginBody:
    """Build an OTP Login V2 request from a caller-supplied client signature."""
    payload = get_client_signature_message_for_login_v2(
        verification_token,
        login_usage,
    )
    _validate_client_signature(payload, client_signature)

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
    verification_token: str,
    signup_usage: v1SignupUsageV3,
    client_signature: v1ClientSignature,
    *,
    timestamp_ms: Optional[str] = None,
) -> CreateSubOrganizationBody:
    """Build a Create Sub Organization V8 request from a client signature."""
    payload = get_client_signature_message_for_signup_v3(
        verification_token,
        signup_usage,
    )
    _validate_client_signature(payload, client_signature)

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
