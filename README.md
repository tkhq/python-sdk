# Turnkey Python SDK

Python SDK for interacting with the Turnkey API.

## 📦 Packages

This is a monorepo containing multiple packages:

- **`turnkey-sdk-types`** - Pydantic type definitions for Turnkey API
- **`turnkey-http`** - HTTP client for making API requests
- **`turnkey-api-key-stamper`** - API key authentication stamper

## 🚀 Quick Start

### Installation

```bash
pip install turnkey-http turnkey-api-key-stamper
```

### Usage

```python
from turnkey_http import TurnkeyClient
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig

# Initialize stamper
config = ApiKeyStamperConfig(
    api_public_key="your-api-public-key",
    api_private_key="your-api-private-key"
)
stamper = ApiKeyStamper(config)

# Create client
client = TurnkeyClient(
    base_url="https://api.turnkey.com",
    stamper=stamper,
    organization_id="your-org-id"
)

# Make API calls
response = client.get_whoami()
print(response)
```

## 💻 Development Setup

### Prerequisites

- Python 3.8+
- pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/tkhq/python-sdk.git
cd python-sdk
```

2. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install all packages in editable mode:
```bash
make install
```

This installs all packages with their dev dependencies in editable mode, so changes take effect immediately.


### Code Generation

This SDK uses code generation to stay in sync with the Turnkey API:

```bash
make generate          # Generate both types and HTTP client
# or
make generate-types    # Generate types only
make generate-http     # Generate HTTP client only
```

### Testing

```bash
make test
```

## 📝 Project Structure

```
python-sdk/
├── packages/
│   ├── sdk-types/         # Type definitions
│   │   ├── src/
│   │   └── scripts/       # Code generator
│   ├── http/              # HTTP client
│   │   ├── src/
│   │   ├── scripts/       # Code generator
│   │   └── tests/
│   └── api-key-stamper/   # Authentication
│       └── src/
├── schema/                # OpenAPI spec
└── examples/              # Example usage
```

