import json
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from enum import Enum

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class SignatureFormat(str, Enum):
    """Supported P-256 signature encodings."""

    DER = "DER"
    RAW = "RAW"


@dataclass
class ApiKeyStamperConfig:
    """Configuration for API key stamper."""

    api_public_key: str
    api_private_key: str


@dataclass
class TStamp:
    """Stamp result containing header name and value."""

    stamp_header_name: str
    stamp_header_value: str


def _sign_with_api_key(
    public_key: str,
    private_key: str,
    content: str,
    signature_format: SignatureFormat = SignatureFormat.DER,
) -> str:
    """Sign content with an API key and validate that the key pair matches.

    Args:
        public_key: Expected public key (compressed, hex format)
        private_key: Private key (hex format)
        content: Content to sign
        signature_format: DER (default) or fixed-width raw r || s

    Returns:
        Hex-encoded signature

    Raises:
        ValueError: If the public key doesn't match the private key
    """
    ec_private_key = ec.derive_private_key(
        int(private_key, 16), ec.SECP256R1(), default_backend()
    )

    public_key_obj = ec_private_key.public_key()
    public_key_bytes = public_key_obj.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint,
    )
    derived_public_key = public_key_bytes.hex()

    if derived_public_key != public_key:
        raise ValueError(
            f"Bad API key. Expected to get public key {public_key}, "
            f"got {derived_public_key}"
        )

    signature = ec_private_key.sign(content.encode(), ec.ECDSA(hashes.SHA256()))
    signature_format = SignatureFormat(signature_format)
    if signature_format == SignatureFormat.RAW:
        r, s = decode_dss_signature(signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    return signature.hex()


class ApiKeyStamper:
    """Stamps requests to the Turnkey API for authentication using API keys."""

    def __init__(self, config: ApiKeyStamperConfig):
        """Initialize the stamper with API key configuration.

        Args:
            config: API key stamper configuration
        """
        self.api_public_key = config.api_public_key
        self.api_private_key = config.api_private_key
        self.stamp_header_name = "X-Stamp"

    def sign(
        self,
        content: str,
        signature_format: SignatureFormat = SignatureFormat.DER,
    ) -> str:
        """Sign content with SHA-256/P-256 in the requested encoding.

        DER remains the default for API request stamps. Use ``SignatureFormat.RAW``
        for fixed-width, 64-byte ``r || s`` client signatures.
        """
        return _sign_with_api_key(
            self.api_public_key,
            self.api_private_key,
            content,
            signature_format,
        )

    def stamp(self, content: str) -> TStamp:
        """Create an authentication stamp for the given content.

        Args:
            content: The request content/payload to stamp (as JSON string)

        Returns:
            TStamp object with header name and base64url-encoded stamp value
        """
        signature = _sign_with_api_key(
            self.api_public_key,
            self.api_private_key,
            content,
            SignatureFormat.DER,
        )

        stamp = {
            "publicKey": self.api_public_key,
            "scheme": "SIGNATURE_SCHEME_TK_API_P256",
            "signature": signature,
        }

        stamp_header_value = (
            urlsafe_b64encode(json.dumps(stamp).encode()).decode().rstrip("=")
        )

        return TStamp(
            stamp_header_name=self.stamp_header_name,
            stamp_header_value=stamp_header_value,
        )
