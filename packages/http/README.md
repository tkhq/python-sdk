# Turnkey HTTP

HTTP client for the Turnkey API with auto-generated methods from the OpenAPI specification.

## Installation

```bash
pip install turnkey-http
```

Or install from the repository in editable mode:

```bash
pip install -e packages/http
```

## Usage

```python
from turnkey_http import TurnkeyClient
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig

# Initialize the stamper
config = ApiKeyStamperConfig(
    api_public_key="your-api-public-key", api_private_key="your-api-private-key"
)
stamper = ApiKeyStamper(config)

# Create the HTTP client
client = TurnkeyClient(
    base_url="https://api.turnkey.com", stamper=stamper, organization_id="your-org-id"
)

# Make API calls with typed methods
response = client.get_whoami()
print(response)
```

## Strict OTP login and signup

The key bound into the verification token must sign the strict token usage. Keep this client-message signer separate from the `ApiKeyStamper` used for normal HTTP request stamps.

The SDK constructs the message but does not sign it. Your application can keep the client key in an HSM, KMS, secure enclave, or other non-extractable store. The signer must return a SHA-256/P-256 signature as fixed-width `r[32] || s[32]`, hex encoded.

```python
from turnkey_http import (
    build_strict_otp_login_request,
    build_strict_otp_signup_request,
    get_client_signature_message_for_login_v2,
    get_client_signature_message_for_signup_v3,
)
from turnkey_sdk_types import (
    v1ClientSignature,
    v1ClientSignatureScheme,
    v1LoginUsageV2,
    v1RootUserParamsV5,
    v1SignupUsageV3,
)


def sign_with_external_p256_key(public_key: str, message: str) -> str:
    # Application-owned HSM/KMS callback. Resolve the non-extractable key by its
    # public key and return a 64-byte raw r || s signature as 128 hex characters.
    raise NotImplementedError


# `client` is a TurnkeyClient configured with its normal HTTP request stamper.
# That request stamper does not sign either client-signature message below.
verification_token = "<verified-otp-jwt>"
login_usage = v1LoginUsageV2(
    organizationId="<sub-organization-id>",
    publicKey="<new-session-public-key>",
    invalidateExisting=False,
    expirationSeconds="3600",
    sessionProfileId="<optional-session-profile-id>",
)
login_payload = get_client_signature_message_for_login_v2(
    verification_token, login_usage
)
login_client_signature = v1ClientSignature(
    publicKey=login_payload.public_key,
    scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
    message=login_payload.message,
    signature=sign_with_external_p256_key(
        login_payload.public_key, login_payload.message
    ),
)
login_body = build_strict_otp_login_request(
    verification_token, login_usage, login_client_signature
)
login_response = client.otp_login(login_body)

signup_usage = v1SignupUsageV3(
    parentOrganizationId="<parent-organization-id>",
    subOrganizationName="Alice's organization",
    rootUsers=[
        v1RootUserParamsV5(
            userName="Alice",
            userEmail="alice@example.com",
            apiKeys=[],
            authenticators=[],
            oauthProviders=[],
        )
    ],
    rootQuorumThreshold=1,
    disableEmailRecovery=False,
)
signup_payload = get_client_signature_message_for_signup_v3(
    verification_token, signup_usage
)
signup_client_signature = v1ClientSignature(
    publicKey=signup_payload.public_key,
    scheme=v1ClientSignatureScheme.CLIENT_SIGNATURE_SCHEME_API_P256,
    message=signup_payload.message,
    signature=sign_with_external_p256_key(
        signup_payload.public_key, signup_payload.message
    ),
)
signup_body = build_strict_otp_signup_request(
    verification_token, signup_usage, signup_client_signature
)
signup_response = client.create_sub_organization(signup_body)
```

## Code Generation

This package uses code generation to create HTTP client methods from the OpenAPI specification located in `schema/public_api.swagger.json`.

### Generate Client

To regenerate the HTTP client:

```bash
cd packages/http
python3 scripts/generate.py
```

The generator automatically formats code with `ruff`.

### Development Setup

Install with dev dependencies:

```bash
pip install -e ".[dev]"
```

## Structure

```
http/
├── src/
│   └── turnkey_http/
│       ├── __init__.py
│       └── generated/         # Auto-generated client (do not edit manually)
├── scripts/
│   └── generate.py           # Code generation script
├── tests/                    # Test suite
├── pyproject.toml
└── README.md
```

## Dependencies

- Python >= 3.8
- requests >= 2.31.0
- turnkey-api-key-stamper
- turnkey-sdk-types

## Development

The generated client is created from the OpenAPI specification with:
- Typed methods for each API endpoint
- Automatic request signing via stamper integration
- Type hints using types from `turnkey-sdk-types`

**Important:** Never edit files in `src/turnkey_http/generated/` manually. They will be overwritten on the next generation run.
