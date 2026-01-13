#!/usr/bin/env python3
"""Generate type definitions from OpenAPI specification."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add codegen directory to Python path
CODEGEN_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CODEGEN_DIR))

from pydantic_helpers import needs_field_alias, safe_property_name
from constants import (
    COMMENT_HEADER,
    METHODS_WITH_ONLY_OPTIONAL_PARAMETERS,
)
from utils import (
    extract_latest_versions,
    method_type_from_method_name,
    get_versioned_intent_type,
    get_versioned_result_type,
)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema" / "public_api.swagger.json"
OUTPUT_DIR = (
    PROJECT_ROOT / "packages" / "sdk-types" / "src" / "turnkey_sdk_types" / "generated"
)
OUTPUT_FILE = OUTPUT_DIR / "types.py"


def swagger_type_to_python(swagger_type: str, schema: Dict[str, Any]) -> str:
    """Convert Swagger type to Python type hint."""
    if swagger_type in ("integer", "number"):
        return "int"
    if swagger_type == "boolean":
        return "bool"
    if swagger_type == "string":
        return "str"
    if swagger_type == "array":
        if "items" in schema:
            if "$ref" in schema["items"]:
                return f"List[{ref_to_python(schema['items']['$ref'])}]"
            elif "type" in schema["items"]:
                return f"List[{swagger_type_to_python(schema['items']['type'], schema['items'])}]"
        return "List[Any]"
    if swagger_type == "object":
        return "Dict[str, Any]"
    return "Any"


def ref_to_python(ref: str) -> str:
    """Convert $ref to Python type name."""
    return ref.replace("#/definitions/", "")


def strip_version_suffix(activity_type: str) -> str:
    """Remove version suffix from activity type."""
    return re.sub(r"(_V\d+)$", "", activity_type)


def is_valid_identifier(name: str) -> bool:
    """Check if a string is a valid Python identifier."""
    return name.isidentifier()


def generate_python_type(name: str, definition: Dict[str, Any]) -> str:
    """Generate Pydantic model from Swagger definition."""
    if definition.get("type") == "object" and (
        "properties" in definition or "additionalProperties" in definition
    ):
        output = f"class {name}(TurnkeyBaseModel):\n"

        if "properties" in definition:
            required = definition.get("required", [])
            for prop, schema in definition["properties"].items():
                prop_type = "Any"
                if "$ref" in schema:
                    prop_type = ref_to_python(schema["$ref"])
                elif "type" in schema:
                    prop_type = swagger_type_to_python(schema["type"], schema)

                # Make field optional if not required
                is_required = prop in required
                if not is_required:
                    prop_type = f"Optional[{prop_type}]"

                desc = schema.get("description", "")
                safe_prop = safe_property_name(prop)
                needs_alias, original_prop = needs_field_alias(prop)

                # Build Field definition
                if needs_alias:
                    field_params = []
                    if not is_required:
                        field_params.append("default=None")
                    field_params.append(f'alias="{original_prop}"')
                    if desc:
                        field_params.append(f'description="{desc}"')
                    field_def = f"Field({', '.join(field_params)})"
                    output += f"    {safe_prop}: {prop_type} = {field_def}\n"
                elif desc or not is_required:
                    field_params = []
                    if not is_required:
                        field_params.append("default=None")
                    if desc:
                        field_params.append(f'description="{desc}"')
                    field_def = f"Field({', '.join(field_params)})"
                    output += f"    {safe_prop}: {prop_type} = {field_def}\n"
                else:
                    # Required field with no description or alias: bare annotation
                    output += f"    {safe_prop}: {prop_type}\n"

        if not definition.get("properties"):
            output += "    pass\n"

        return output + "\n"

    if definition.get("type") == "string" and "enum" in definition:
        # Generate proper enum members: MEMBER_NAME = "MEMBER_VALUE"
        enum_members = []
        for e in definition["enum"]:
            # Use the enum value as both the member name and value
            # This allows both EnumClass.MEMBER_NAME and "MEMBER_VALUE" string to work
            enum_members.append(f'{e} = "{e}"')
        enum_values = "\n    ".join(enum_members)
        return f"class {name}(str, Enum):\n    {enum_values}\n\n"

    return f"class {name}(TurnkeyBaseModel):\n    pass\n\n"


def generate_inline_properties(
    definition: Optional[Dict[str, Any]], is_all_optional: bool = False
) -> str:
    """Generate inline Pydantic properties."""
    output = ""
    if definition and "properties" in definition:
        required_props = definition.get("required", [])
        for prop, schema in definition["properties"].items():
            prop_type = "Any"
            if "$ref" in schema:
                prop_type = ref_to_python(schema["$ref"])
            elif "type" in schema:
                prop_type = swagger_type_to_python(schema["type"], schema)

            # For activity response types, result fields should be optional since they're only present when completed
            is_required = prop in required_props and not is_all_optional
            if not is_required:
                prop_type = f"Optional[{prop_type}]"

            desc = schema.get("description", "")
            safe_prop = safe_property_name(prop)
            needs_alias, original_prop = needs_field_alias(prop)

            # Build Field definition
            if needs_alias:
                field_params = []
                if not is_required:
                    field_params.append("default=None")
                field_params.append(f'alias="{original_prop}"')
                if desc:
                    field_params.append(f'description="{desc}"')
                field_def = f"Field({', '.join(field_params)})"
                output += f"    {safe_prop}: {prop_type} = {field_def}\n"
            elif desc or not is_required:
                field_params = []
                if not is_required:
                    field_params.append("default=None")
                if desc:
                    field_params.append(f'description="{desc}"')
                field_def = f"Field({', '.join(field_params)})"
                output += f"    {safe_prop}: {prop_type} = {field_def}\n"
            else:
                # Required field with no description or alias: bare annotation
                output += f"    {safe_prop}: {prop_type}\n"

    return output


def generate_api_types(swagger: Dict[str, Any], prefix: str = "") -> str:
    """Generate API types from Swagger paths."""
    namespace = next(
        (tag["name"] for tag in swagger.get("tags", []) if "name" in tag), None
    )
    output = ""
    latest_versions = extract_latest_versions(swagger["definitions"])
    definitions = swagger["definitions"]

    for path, methods in swagger["paths"].items():
        operation = methods.get("post")
        if not operation:
            continue

        operation_id = operation.get("operationId")
        if not operation_id:
            continue

        operation_name_without_namespace = operation_id.replace(f"{namespace}_", prefix)
        method_name = (
            operation_name_without_namespace[0].lower()
            + operation_name_without_namespace[1:]
        )
        method_type = method_type_from_method_name(method_name)

        # Get response schema
        response_schema = None
        if "responses" in operation and "200" in operation["responses"]:
            response_schema = (
                operation["responses"]["200"].get("schema", {}).get("$ref")
            )
        response_type_name = ref_to_python(response_schema) if response_schema else None

        # Compose API type names
        api_type_name = (
            operation_name_without_namespace[0].upper()
            + operation_name_without_namespace[1:]
            + "Response"
        )
        api_body_type_name = (
            operation_name_without_namespace[0].upper()
            + operation_name_without_namespace[1:]
            + "Body"
        )
        api_input_type_name = (
            operation_name_without_namespace[0].upper()
            + operation_name_without_namespace[1:]
            + "Input"
        )

        # --- RESPONSE TYPE GENERATION ---
        if method_type == "activity":
            result_type_name = None
            activity_type_key = None
            version_suffix = None

            parameters = operation.get("parameters", [])
            for param in parameters:
                if param.get("in") == "body" and "$ref" in param.get("schema", {}):
                    req_type_name = ref_to_python(param["schema"]["$ref"])
                    req_def = definitions.get(req_type_name)
                    if (
                        req_def
                        and "properties" in req_def
                        and "type" in req_def["properties"]
                    ):
                        type_prop = req_def["properties"]["type"]
                        if "enum" in type_prop and type_prop["enum"]:
                            activity_type_key = strip_version_suffix(
                                type_prop["enum"][0]
                            )
                            versioned_result = get_versioned_result_type(
                                activity_type_key
                            )

                            base_activity = re.sub(r"^v\d+", "", req_type_name)
                            base_activity = re.sub(
                                r"Request(V\d+)?$", "", base_activity
                            )
                            result_base = base_activity + "Result"
                            result_key = None

                            if result_base in latest_versions:
                                # Use mapped result type directly if available
                                if versioned_result and versioned_result in definitions:
                                    result_key = versioned_result
                                if not result_key:
                                    result_key = latest_versions[result_base][
                                        "full_name"
                                    ]

                            if result_key:
                                result_type_name = result_key

            output += f"class {api_type_name}(TurnkeyBaseModel):\n"
            output += "    activity: v1Activity\n"
            if result_type_name and result_type_name in definitions:
                # Include result fields as required - they're present when function returns successfully
                result_props = generate_inline_properties(
                    definitions[result_type_name], is_all_optional=False
                )
                if result_props.strip():  # Only add if there are actual properties
                    output += result_props
            output += "\n\n"

        elif method_type in ("query", "noop"):
            resp_def = (
                definitions.get(response_type_name) if response_type_name else None
            )
            if resp_def:
                if "properties" in resp_def:
                    output += f"class {api_type_name}(TurnkeyBaseModel):\n"
                    output += generate_inline_properties(resp_def)
                    output += "\n\n"
                else:
                    output += f"class {api_type_name}(TurnkeyBaseModel):\n    pass\n\n"

        elif method_type == "activityDecision":
            activity_type = (
                definitions.get(response_type_name) if response_type_name else None
            )
            if activity_type and "properties" in activity_type:
                output += f"class {api_type_name}(TurnkeyBaseModel):\n"
                output += generate_inline_properties(activity_type)
                output += "\n\n"

        # --- REQUEST TYPE GENERATION ---
        request_type_def = None
        request_type_name = None
        parameters = operation.get("parameters", [])

        for param in parameters:
            if param.get("in") == "body" and "$ref" in param.get("schema", {}):
                request_type_name = ref_to_python(param["schema"]["$ref"])
                request_type_def = definitions.get(request_type_name)

        if not request_type_def:
            continue

        output += f"class {api_body_type_name}(TurnkeyBaseModel):\n"

        if method_type in ("activity", "activityDecision"):
            output += "    timestampMs: Optional[str] = None\n"
            output += "    organizationId: Optional[str] = None\n"

            if (
                "properties" in request_type_def
                and "parameters" in request_type_def["properties"]
            ):
                params_prop = request_type_def["properties"]["parameters"]
                if "$ref" in params_prop:
                    is_all_optional = (
                        method_name in METHODS_WITH_ONLY_OPTIONAL_PARAMETERS
                    )
                    intent_type_name = ref_to_python(params_prop["$ref"])

                    base_activity = re.sub(r"^v\d+", "", request_type_name).replace(
                        re.compile(r"Request(V\d+)?$").pattern, ""
                    )
                    activity_type_key = strip_version_suffix(
                        request_type_def["properties"]["type"]["enum"][0]
                    )
                    versioned_intent = get_versioned_intent_type(activity_type_key)

                    adjusted_intent_type_name = intent_type_name
                    if versioned_intent and versioned_intent in definitions:
                        adjusted_intent_type_name = versioned_intent

                    intent_def = definitions.get(adjusted_intent_type_name)
                    output += generate_inline_properties(intent_def, is_all_optional)

        elif method_type in ("query", "noop"):
            output += "    organizationId: Optional[str] = None\n"
            if "properties" in request_type_def:
                is_all_optional = method_name in METHODS_WITH_ONLY_OPTIONAL_PARAMETERS
                required_props = request_type_def.get("required", [])
                for prop, schema in request_type_def["properties"].items():
                    if prop == "organizationId":
                        continue
                    prop_type = "Any"
                    if "$ref" in schema:
                        prop_type = ref_to_python(schema["$ref"])
                    elif "type" in schema:
                        prop_type = swagger_type_to_python(schema["type"], schema)

                    # Check if field is required
                    is_required = prop in required_props and not is_all_optional
                    if not is_required:
                        prop_type = f"Optional[{prop_type}]"

                    desc = schema.get("description", "")
                    safe_prop = safe_property_name(prop)
                    needs_alias, original_prop = needs_field_alias(prop)

                    # Build Field definition
                    if needs_alias:
                        field_params = []
                        if not is_required:
                            field_params.append("default=None")
                        field_params.append(f'alias="{original_prop}"')
                        if desc:
                            field_params.append(f'description="{desc}"')
                        field_def = f"Field({', '.join(field_params)})"
                        output += f"    {safe_prop}: {prop_type} = {field_def}\n"
                    elif desc or not is_required:
                        field_params = []
                        if not is_required:
                            field_params.append("default=None")
                        if desc:
                            field_params.append(f'description="{desc}"')
                        field_def = f"Field({', '.join(field_params)})"
                        output += f"    {safe_prop}: {prop_type} = {field_def}\n"
                    else:
                        # Required field with no description or alias: bare annotation
                        output += f"    {safe_prop}: {prop_type}\n"

        output += "\n\n"
        output += f"class {api_input_type_name}(TurnkeyBaseModel):\n"
        output += f"    body: {api_body_type_name}\n\n\n"

    return output


def main():
    """Generate types from OpenAPI spec."""
    print("🔧 Turnkey SDK Types Generator")
    print("=" * 50)

    # Check if schema file exists
    if not SCHEMA_PATH.exists():
        print(f"❌ Error: Schema file not found at {SCHEMA_PATH}")
        print(
            f"   Please ensure public_api.swagger.json exists in the schema directory"
        )
        return 1

    print(f"📄 Schema: {SCHEMA_PATH}")
    print(f"📁 Output: {OUTPUT_FILE}")
    print()

    # Load swagger
    with open(SCHEMA_PATH, "r") as f:
        swagger_main = json.load(f)

    print(f"✓ Loaded OpenAPI spec")

    # Generate output
    output = f"{COMMENT_HEADER}\n\n"
    output += "from __future__ import annotations\n"
    output += "from typing import Any, Dict, List, Optional\n"
    output += "from enum import Enum\n"
    output += "from pydantic import BaseModel, Field, ConfigDict\n\n"
    output += "\n# Base class with shared configuration\n"
    output += "class TurnkeyBaseModel(BaseModel):\n"
    output += "    model_config = ConfigDict(populate_by_name=True)\n\n"

    # --- Base Types ---
    output += "# --- Base Types from Swagger Definitions ---\n\n"

    for def_name, definition in swagger_main["definitions"].items():
        if (definition.get("type") == "object" and "properties" in definition) or (
            definition.get("type") == "string" and "enum" in definition
        ):
            output += generate_python_type(def_name, definition)
        else:
            output += f"class {def_name}(TurnkeyBaseModel):\n    pass\n\n"

    # --- API Types ---
    output += "\n# --- API Types from Swagger Paths ---\n\n"
    output += generate_api_types(swagger_main)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        f.write(output)

    print(f"✅ Generated {OUTPUT_FILE}")
    print(f"   {len(swagger_main['definitions'])} base types")
    print(f"   {len(swagger_main['paths'])} API endpoints")

    # Format with ruff
    print()
    print("🎨 Formatting with ruff...")
    try:
        subprocess.run(
            ["ruff", "format", str(OUTPUT_FILE)],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ Formatted {OUTPUT_FILE}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Formatting failed: {e.stderr}")
    except FileNotFoundError:
        print("⚠️  ruff not found - skipping formatting")
        print("   Install with: pip install ruff")

    return 0


if __name__ == "__main__":
    sys.exit(main())
