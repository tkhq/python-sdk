import json
from base64 import urlsafe_b64decode

import turnkey_api_key_stamper
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig


def test_stamp_keeps_existing_der_request_signature_behavior():
    private_key = ec.derive_private_key(1, ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    )
    stamper = ApiKeyStamper(
        ApiKeyStamperConfig(
            api_public_key=public_key.hex(),
            api_private_key="01",
        )
    )
    content = '{"organizationId":"org-id"}'

    assert not hasattr(turnkey_api_key_stamper, "SignatureFormat")
    assert not hasattr(stamper, "sign")
    stamp = stamper.stamp(content)

    encoded = stamp.stamp_header_value + "=" * (-len(stamp.stamp_header_value) % 4)
    payload = json.loads(urlsafe_b64decode(encoded))
    assert payload["publicKey"] == public_key.hex()
    assert payload["scheme"] == "SIGNATURE_SCHEME_TK_API_P256"
    signature = bytes.fromhex(payload["signature"])
    r, s = decode_dss_signature(signature)
    assert r > 0
    assert s > 0
    private_key.public_key().verify(
        signature,
        content.encode(),
        ec.ECDSA(hashes.SHA256()),
    )
