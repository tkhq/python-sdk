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
    api_public_key="your-api-public-key",
    api_private_key="your-api-private-key"
)
stamper = ApiKeyStamper(config)

# Create the HTTP client
client = TurnkeyClient(
    base_url="https://api.turnkey.com",
    stamper=stamper,
    organization_id="your-org-id"
)

# Make API calls with typed methods
response = client.get_whoami()
print(response)
```

## Handling activity outcomes

Activity methods poll until the activity finishes. If it does not complete, they raise an error. `TurnkeyActivityConsensusNeededError` means the activity needs more approvals. `TurnkeyActivityAuthenticatorsNeededError` means it needs authenticator approval. `TurnkeyActivityError` means it failed, was rejected, or was still pending when polling stopped. These errors carry `activity_id`, `activity_status`, `activity_type`, and `failure`. Catch the subclasses first, because they extend `TurnkeyActivityError`.

Consensus-needed and authenticators-needed each stop the normal activity poll. Pass a `PollingConfig` as `consensus_polling` or `mfa_polling` to keep polling that status. The MFA interval doubles on each attempt, up to 5 seconds. The consensus interval stays fixed. Omit a config to raise that status's error immediately. A timeout raises the same error. Use `activity_id` with `get_activity` after the missing approvals are in place.

```python
from turnkey_http import PollingConfig, TurnkeyClient
from turnkey_sdk_types import (
    TurnkeyActivityAuthenticatorsNeededError,
    TurnkeyActivityConsensusNeededError,
    TurnkeyActivityError,
)

client = TurnkeyClient(
    base_url="https://api.turnkey.com",
    stamper=stamper,
    organization_id="your-org-id",
    consensus_polling=PollingConfig(interval_ms=500, timeout_ms=30_000),
    mfa_polling=PollingConfig(interval_ms=500, timeout_ms=30_000),
)

try:
    response = ...  # any activity method
except TurnkeyActivityConsensusNeededError as err:
    activity_id = err.activity_id
except TurnkeyActivityAuthenticatorsNeededError as err:
    activity_id = err.activity_id
except TurnkeyActivityError as err:
    print(err.activity_status, err.failure)
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

- Python >= 3.11
- requests >= 2.31.0
- turnkey-api-key-stamper
- turnkey-sdk-types

## Development

The generated client is created from the OpenAPI specification with:
- Typed methods for each API endpoint
- Automatic request signing via stamper integration
- Type hints using types from `turnkey-sdk-types`

**Important:** Never edit files in `src/turnkey_http/generated/` manually. They will be overwritten on the next generation run.
