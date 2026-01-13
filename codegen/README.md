# Codegen

Internal code generation scripts for the Turnkey Python SDK.

This directory contains utilities and scripts to generate:
- Type definitions from OpenAPI spec
- HTTP client from OpenAPI spec

## Usage

These scripts are called via the Makefile:

```bash
make generate        # Generate all code
make generate-types  # Generate type definitions only
make generate-http   # Generate HTTP client only
```

## Structure

- `utils.py` - Shared utilities and constants
- `pydantic_helpers.py` - Helper functions for Pydantic model generation
- `generate_types.py` - Generates type definitions
- `generate_http.py` - Generates HTTP client

This is not a package and is not published to PyPI. It's only used during development.
