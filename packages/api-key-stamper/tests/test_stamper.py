import json
from base64 import urlsafe_b64decode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from turnkey_api_key_stamper import (
    ApiKeyStamper,
    ApiKeyStamperConfig,
    SignatureFormat,
)


def _stamper():
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


def test_stamp_keeps_der_signature_format():
    content = '{"organizationId":"org-id"}'
    stamper = _stamper()

    stamp = stamper.stamp(content)
    encoded = stamp.stamp_header_value + "=" * (-len(stamp.stamp_header_value) % 4)
    payload = json.loads(urlsafe_b64decode(encoded))
    signature = bytes.fromhex(payload["signature"])

    r, s = decode_dss_signature(signature)
    assert r > 0
    assert s > 0
    stamper_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(stamper.api_public_key)
    )
    stamper_public_key.verify(signature, content.encode(), ec.ECDSA(hashes.SHA256()))


def test_explicit_raw_signature_is_fixed_width_and_verifies():
    content = "strict token usage"
    stamper = _stamper()

    signature_hex = stamper.sign(content, SignatureFormat.RAW)
    signature = bytes.fromhex(signature_hex)

    assert len(signature_hex) == 128
    assert len(signature) == 64
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    der_signature = encode_dss_signature(r, s)
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(stamper.api_public_key)
    )
    public_key.verify(der_signature, content.encode(), ec.ECDSA(hashes.SHA256()))
