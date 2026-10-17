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
- `constants.py` - Pinned activity versions (`VERSIONED_ACTIVITY_TYPES`) and other fixed tables
- `activity_versions.json` - Snapshot of the activity type each client method sends

## Activity versions

Unpinned activities take their version from the schema's request definition, so a new schema can move a method to a new version. `make generate-http` compares the versions it is about to emit with `activity_versions.json` and stops if any method moved. To keep the old version, pin it in `constants.py`. To accept the move, list it in the PR and rerun with `CODEGEN_ACCEPT_VERSION_CHANGES=1 make generate-http`, which rewrites the snapshot.

This is not a package and is not published to PyPI. It's only used during development.
