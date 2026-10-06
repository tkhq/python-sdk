import json
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from typing import Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend


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


def _sign_with_api_key(public_key: str, private_key: str, content: str) -> str:
    """Sign content with API key and validate public key matches.

    Args:
        public_key: Expected public key (compressed, hex format)
        private_key: Private key (hex format)
        content: Content to sign

    Returns:
        Hex-encoded signature

    Raises:
        ValueError: If public key doesn't match private key
    """
    # Derive private key from hex
    ec_private_key = ec.derive_private_key(
        int(private_key, 16), ec.SECP256R1(), default_backend()
    )

    # Get the public key from the private key to validate
    public_key_obj = ec_private_key.public_key()
    public_key_bytes = public_key_obj.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint,
    )
    derived_public_key = public_key_bytes.hex()

    # Validate that the provided public key matches
    if derived_public_key != public_key:
        raise ValueError(
            f"Bad API key. Expected to get public key {public_key}, "
            f"got {derived_public_key}"
        )

    # Sign the content
    signature = ec_private_key.sign(content.encode(), ec.ECDSA(hashes.SHA256()))

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

    def stamp(self, content: str) -> TStamp:
        """Create an authentication stamp for the given content.

        Args:
            content: The request content/payload to stamp (as JSON string)

        Returns:
            TStamp object with header name and base64url-encoded stamp value
        """
        signature = _sign_with_api_key(
            self.api_public_key, self.api_private_key, content
        )

        stamp = {
            "publicKey": self.api_public_key,
            "scheme": "SIGNATURE_SCHEME_TK_API_P256",
            "signature": signature,
        }

        # Encode stamp to base64url
        stamp_header_value = (
            urlsafe_b64encode(json.dumps(stamp).encode()).decode().rstrip("=")
        )

        return TStamp(
            stamp_header_name=self.stamp_header_name,
            stamp_header_value=stamp_header_value,
        )
