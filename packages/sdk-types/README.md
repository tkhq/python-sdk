# Turnkey SDK Types

Generated type definitions for the Turnkey API based on the OpenAPI specification.

## Why Pydantic?

This package uses Pydantic models to handle field name conflicts with Python keywords. For example, some Turnkey API requests include a `from` field (like `v1EthSendTransactionIntent`), which is a reserved keyword in Python. 

Pydantic's Field aliasing allows us to:
- Use `from_` in Python code (avoiding syntax errors)
- Automatically serialize to `from` when making API requests to Turnkey

```python
class v1EthSendTransactionIntent(TurnkeyBaseModel):
    from_: str = Field(alias="from")
    # ... other fields
```

## Installation

```bash
pip install -e .
```

Or install from the repository root:

```bash
pip install -e packages/sdk-types
```

## Usage

```python
from turnkey_sdk_types import (
    # Generated types will be available here
    # Example: CreateApiKeyRequest, CreateApiKeyResponse, etc.
)
```

## Code Generation

This package uses code generation to create type definitions from the OpenAPI specification located in `schema/public_api.swagger.json`.

### Generate Types

To regenerate the types:

```bash
cd packages/sdk-types
python scripts/generate.py
```

### Development Setup

Install with dev dependencies to access code generation tools:

```bash
pip install -e ".[dev]"
```

## Structure

```
sdk-types/
├── src/
│   └── turnkey_sdk_types/
│       ├── __init__.py        # Package exports
│       ├── types.py           # RequestType, SignedRequest (not generated)
│       ├── errors.py          # TurnkeyError, TurnkeyNetworkError (not generated)
│       └── generated/         # Auto-generated from OpenAPI spec
│           └── types.py       
├── scripts/
│   └── generate.py           # Code generation script
├── pyproject.toml
└── README.md
```

## Requirements

- Python >= 3.8

## Development

### Generated Types

The types in `generated/types.py` are automatically created from the OpenAPI specification at `schema/public_api.swagger.json`. These include all request/response models like `v1EthSendTransactionIntent`, `CreateWalletBody`, etc.

**Important:** Never edit files in `src/turnkey_sdk_types/generated/` manually. They will be overwritten on the next generation run.

### Non-Generated Types

Files outside the `generated/` directory are maintained as part of the SDK and are not auto-generated:
- `types.py` - Core SDK types like `RequestType`, `SignedRequest`
- `errors.py` - Error classes like `TurnkeyError`, `TurnkeyNetworkError`
