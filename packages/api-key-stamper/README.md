# Turnkey API Key Stamper

Authentication utility for Turnkey API requests. The stamper signs requests with your API key credentials.

## Installation

```bash
pip install turnkey-api-key-stamper
```

## Usage

```python
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
import requests
import json

# Initialize the stamper with your API credentials
config = ApiKeyStamperConfig(
    api_public_key="<Turnkey API Public Key (that starts with 02 or 03)>",
    api_private_key="<Turnkey API Private Key>"
)
stamper = ApiKeyStamper(config)

# Create your request payload
payload = {
    "organizationId": "<your org ID>"
}
payload_str = json.dumps(payload)

# Generate the authentication stamp
stamp = stamper.stamp(payload_str)
```

