# Turnkey SDK Types

Generated type definitions for the Turnkey API based on the OpenAPI specification.

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
│       ├── __init__.py
│       └── generated/         # Auto-generated types (do not edit manually)
├── scripts/
│   └── generate.py           # Code generation script
├── pyproject.toml
└── README.md
```

## Requirements

- Python >= 3.8

## Development

The generated types are created using `datamodel-code-generator` which creates Pydantic models from the OpenAPI specification.

**Important:** Never edit files in `src/turnkey_sdk_types/generated/` manually. They will be overwritten on the next generation run.
