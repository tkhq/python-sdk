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
├── tests/
│   └── test_http_client.py
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
