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

The client key pair supplied during OTP verification must sign the strict token usage. The normal `TurnkeyClient` request stamper remains separate and continues to use DER signatures.

```python
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
from turnkey_http import (
    build_strict_otp_login_request,
    build_strict_otp_signup_request,
)
from turnkey_sdk_types import v1RootUserParamsV5

# This key pair must match the public_key claim in the verification token.
client_stamper = ApiKeyStamper(
    ApiKeyStamperConfig(
        api_public_key="<verification-token-client-public-key>",
        api_private_key="<verification-token-client-private-key>",
    )
)

login_body = build_strict_otp_login_request(
    client_stamper,
    verification_token="<verified-otp-jwt>",
    organization_id="<sub-organization-id>",
    public_key="<new-session-public-key>",
    invalidate_existing=False,
    expiration_seconds="3600",
    session_profile_id="<optional-session-profile-id>",
)
login_response = client.otp_login(login_body)

root_user = v1RootUserParamsV5(
    userName="Alice",
    userEmail="alice@example.com",
    apiKeys=[],
    authenticators=[],
    oauthProviders=[],
)
signup_body = build_strict_otp_signup_request(
    client_stamper,
    verification_token="<verified-otp-jwt>",
    parent_organization_id="<parent-organization-id>",
    sub_organization_name="Alice's organization",
    root_users=[root_user],
    root_quorum_threshold=1,
    disable_email_recovery=False,
)
signup_response = client.create_sub_organization(signup_body)
```

The builders create the matching `loginV2` or `signupV3` token usage, compact camelCase message, raw P-256 client signature, and request body from the same typed values.

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
