#!/usr/bin/env python3
"""Generate HTTP client from OpenAPI specification."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

# Add codegen directory to Python path
CODEGEN_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CODEGEN_DIR))

from constants import (
    COMMENT_HEADER,
    VERSIONED_ACTIVITY_TYPES,
    METHODS_WITH_ONLY_OPTIONAL_PARAMETERS,
    TERMINAL_ACTIVITY_STATUSES,
)
from utils import (
    to_snake_case,
    extract_latest_versions,
    method_type_from_method_name,
)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema" / "public_api.swagger.json"
OUTPUT_DIR = PROJECT_ROOT / "packages" / "http" / "src" / "turnkey_http" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "client.py"


def generate_sdk_client(swagger: Dict[str, Any]) -> str:
    """Generate the SDK client from Swagger spec."""
    namespace = next(
        (tag["name"] for tag in swagger.get("tags", []) if "name" in tag), None
    )
    code_buffer = []
    latest_versions = extract_latest_versions(swagger["definitions"])

    # Generate class header
    code_buffer.append("""
class TurnkeyClient:
    \"\"\"Turnkey API HTTP client with auto-generated methods.\"\"\"
    
    def __init__(
        self,
        base_url: str,
        stamper: ApiKeyStamper,
        organization_id: str,
        default_timeout: int = 30,
        polling_interval_ms: int = 1000,
        max_polling_retries: int = 3
    ):
        \"\"\"Initialize the Turnkey client.
        
        Args:
            base_url: Base URL for the Turnkey API
            stamper: API key stamper for authentication
            organization_id: Organization ID
            default_timeout: Default request timeout in seconds
            polling_interval_ms: Polling interval for activity status in milliseconds
            max_polling_retries: Maximum number of polling retries
        \"\"\"
        self.base_url = base_url.rstrip("/")
        self.stamper = stamper
        self.organization_id = organization_id
        self.default_timeout = default_timeout
        self.polling_interval_ms = polling_interval_ms
        self.max_polling_retries = max_polling_retries
    
    def _serialize_body(self, body: Any) -> str:
        \"\"\"Serialize request body, handling Pydantic models recursively.
        
        Args:
            body: Request body (dict, Pydantic model, list, or primitive)
            
        Returns:
            JSON string
        \"\"\"
        def serialize_value(value):
            \"\"\"Recursively serialize values, converting Pydantic models to dicts.\"\"\"
            if hasattr(value, 'model_dump'):
                return value.model_dump(by_alias=True, exclude_none=True)
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize_value(item) for item in value]
            else:
                return value
        
        serialized = serialize_value(body)
        return json.dumps(serialized)
    
    def _request(self, url: str, body: Dict[str, Any], response_type: type) -> Any:
        \"\"\"Make a request to the Turnkey API.
        
        Args:
            url: Endpoint URL
            body: Request body
            response_type: Pydantic model class for response parsing
            
        Returns:
            Parsed response as Pydantic model
            
        Raises:
            TurnkeyNetworkError: If request fails
        \"\"\"
        full_url = self.base_url + url
        body_str = self._serialize_body(body)
        stamp = self.stamper.stamp(body_str)
        
        headers = {
            stamp.stamp_header_name: stamp.stamp_header_value,
            "Content-Type": "application/json",
            "X-Client-Version": VERSION
        }
        
        try:
            response = requests.post(
                full_url,
                headers=headers,
                data=body_str,
                timeout=self.default_timeout
            )
        except requests.RequestException as exc:
            raise TurnkeyNetworkError(
                "Request failed",
                None,
                TurnkeyErrorCodes.NETWORK_ERROR,
                str(exc)
            ) from exc
        
        if not response.ok:
            try:
                error_data = response.json()
                error_message = error_data.get("message", str(error_data))
            except ValueError:
                error_message = response.text or f"{response.status_code} {response.reason}"
            
            raise TurnkeyNetworkError(
                error_message,
                response.status_code,
                TurnkeyErrorCodes.BAD_RESPONSE,
                response.text
            )
        
        response_data = response.json()
        return response_type(**response_data)
    
    def _activity(self, url: str, body: Dict[str, Any], result_key: str, response_type: type) -> Any:
        \"\"\"Execute an activity and poll for completion.
        
        Args:
            url: Endpoint URL
            body: Request body
            result_key: Key to extract result from activity when completed
            response_type: Pydantic model class for response parsing
            
        Returns:
            Parsed response as Pydantic model with flattened result fields
        \"\"\"
        # Make initial request, we parse as activity response without result fields
        initial_response = self._request(url, body, TGetActivityResponse)
        
        # Check if we need to poll
        activity = initial_response.activity
        
        if activity.status not in TERMINAL_ACTIVITY_STATUSES:
            # Poll for completion
            activity_id = activity.id
            attempts = 0
            
            while attempts < self.max_polling_retries:
                time.sleep(self.polling_interval_ms / 1000.0)
                
                # Poll activity status
                poll_response = self.get_activity(TGetActivityBody(activityId=activity_id))
                activity = poll_response.activity
                
                if activity.status in TERMINAL_ACTIVITY_STATUSES:
                    break
                
                attempts += 1
        
        # If activity completed successfully, flatten result fields into response
        if activity.status == "ACTIVITY_STATUS_COMPLETED" and hasattr(activity, 'result') and activity.result:
            result = activity.result
            # Get the versioned result key (e.g., 'createApiKeysResultV2')
            if hasattr(result, result_key):
                result_data = getattr(result, result_key)
                if result_data and hasattr(result_data, 'model_dump'):
                    # Flatten result fields into response
                    result_dict = result_data.model_dump(by_alias=True, exclude_none=True)
                    # Construct final response with activity and result fields
                    response = response_type(
                        activity=activity,
                        **result_dict
                    )
                    return response
        
        # Return response with just the activity (no result fields)
        return response_type(activity=activity)
    
    def _activity_decision(self, url: str, body: Dict[str, Any], response_type: type) -> Any:
        \"\"\"Execute an activity decision.
        
        Args:
            url: Endpoint URL
            body: Request body
            response_type: Pydantic model class for response parsing
            
        Returns:
            Parsed response as Pydantic model
        \"\"\"
        return self._request(url, body, response_type)
""")

    # Generate methods for each endpoint
    for path, methods in swagger["paths"].items():
        operation = methods.get("post")
        if not operation:
            continue

        operation_id = operation.get("operationId")
        if not operation_id:
            continue

        operation_name_without_namespace = operation_id.replace(f"{namespace}_", "")

        if operation_name_without_namespace == "NOOPCodegenAnchor":
            continue

        method_name = (
            operation_name_without_namespace[0].lower()
            + operation_name_without_namespace[1:]
        )
        snake_method_name = to_snake_case(method_name)
        method_type = method_type_from_method_name(method_name)

        # Extract description from OpenAPI spec
        summary = operation.get("summary", "")

        input_type = f"T{operation_name_without_namespace}Body"
        response_type = f"T{operation_name_without_namespace}Response"

        unversioned_activity_type = (
            f"ACTIVITY_TYPE_{to_snake_case(operation_name_without_namespace).upper()}"
        )
        versioned_activity_type = VERSIONED_ACTIVITY_TYPES.get(
            unversioned_activity_type, unversioned_activity_type
        )

        # Generate method
        if method_type == "query":
            has_optional_params = method_name in METHODS_WITH_ONLY_OPTIONAL_PARAMETERS

            if has_optional_params:
                # Method has only optional parameters so we allow None with default
                code_buffer.append(f"""
    def {snake_method_name}(self, input: Optional[{input_type}] = None) -> {response_type}:
        if input is None:
            input_dict = {{}}
        else:
            # Convert Pydantic model to dict
            input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        
        body = {{
            "organizationId": organization_id,
            **input_dict
        }}
        
        return self._request("{path}", body, {response_type})
    
    def stamp_{snake_method_name}(self, input: Optional[{input_type}] = None) -> TSignedRequest:
        \"\"\"Stamp a {method_name} request without sending it.\"\"\"
        
        if input is None:
            input_dict = {{}}
        else:
            # Convert Pydantic model to dict
            input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        
        body = {{
            "organizationId": organization_id,
            **input_dict
        }}
        
        full_url = self.base_url + "{path}"
        body_str = self._serialize_body(body)
        stamp = self.stamper.stamp(body_str)
        
        return TSignedRequest(url=full_url, body=body_str, stamp=stamp)
""")
            else:
                # Method has required parameters so input is required, not Optional
                code_buffer.append(f"""
    def {snake_method_name}(self, input: {input_type}) -> {response_type}:
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        
        body = {{
            "organizationId": organization_id,
            **input_dict
        }}
        
        return self._request("{path}", body, {response_type})
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> TSignedRequest:
        \"\"\"Stamp a {method_name} request without sending it.\"\"\"
        
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        
        body = {{
            "organizationId": organization_id,
            **input_dict
        }}
        
        full_url = self.base_url + "{path}"
        body_str = self._serialize_body(body)
        stamp = self.stamper.stamp(body_str)
        
        return TSignedRequest(url=full_url, body=body_str, stamp=stamp)
""")

        elif method_type == "activity":
            result_key = operation_name_without_namespace + "Result"
            versioned_method_name = latest_versions[result_key]["formatted_key_name"]

            code_buffer.append(f"""
    def {snake_method_name}(self, input: {input_type}) -> {response_type}:
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        timestamp_ms = input_dict.pop("timestampMs", str(int(time.time() * 1000)))
        
        body = {{
            "parameters": input_dict,
            "organizationId": organization_id,
            "timestampMs": timestamp_ms,
            "type": "{versioned_activity_type}"
        }}
        
        return self._activity("{path}", body, "{versioned_method_name}", {response_type})
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> TSignedRequest:
        \"\"\"Stamp a {method_name} request without sending it.\"\"\"
        
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        timestamp_ms = input_dict.pop("timestampMs", str(int(time.time() * 1000)))
        
        body = {{
            "parameters": input_dict,
            "organizationId": organization_id,
            "timestampMs": timestamp_ms,
            "type": "{versioned_activity_type}"
        }}
        
        full_url = self.base_url + "{path}"
        body_str = self._serialize_body(body)
        stamp = self.stamper.stamp(body_str)
        
        return TSignedRequest(url=full_url, body=body_str, stamp=stamp)
""")

        elif method_type == "activityDecision":
            code_buffer.append(f"""
    def {snake_method_name}(self, input: {input_type}) -> {response_type}:
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        timestamp_ms = input_dict.pop("timestampMs", str(int(time.time() * 1000)))
        
        body = {{
            "parameters": input_dict,
            "organizationId": organization_id,
            "timestampMs": timestamp_ms,
            "type": "{unversioned_activity_type}"
        }}
        
        return self._activity_decision("{path}", body, {response_type})
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> TSignedRequest:
        \"\"\"Stamp a {method_name} request without sending it.\"\"\"
        
        # Convert Pydantic model to dict
        input_dict = input.model_dump(by_alias=True, exclude_none=True)
        
        organization_id = input_dict.pop("organizationId", self.organization_id)
        timestamp_ms = input_dict.pop("timestampMs", str(int(time.time() * 1000)))
        
        body = {{
            "parameters": input_dict,
            "organizationId": organization_id,
            "timestampMs": timestamp_ms,
            "type": "{unversioned_activity_type}"
        }}
        
        full_url = self.base_url + "{path}"
        body_str = self._serialize_body(body)
        stamp = self.stamper.stamp(body_str)
        
        return TSignedRequest(url=full_url, body=body_str, stamp=stamp)
""")

    return "\n".join(code_buffer)


def main():
    """Generate HTTP client from OpenAPI spec."""
    print("🔧 Turnkey SDK HTTP Generator")
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
        swagger = json.load(f)

    print(f"✓ Loaded OpenAPI spec")
    print(f"  Found {len(swagger['paths'])} API endpoints")
    print()

    # Generate client
    print("🔨 Generating HTTP client...")
    client_code = generate_sdk_client(swagger)

    # Build full output
    output = f"{COMMENT_HEADER}\n\n"
    output += "import json\nimport time\nfrom typing import Any, Dict, Optional\nimport requests\n"
    output += "from dataclasses import dataclass\n"
    output += "from turnkey_api_key_stamper import ApiKeyStamper, TStamp\n"
    output += "from turnkey_sdk_types import *\n"
    output += "from ..version import VERSION\n\n"
    output += f"TERMINAL_ACTIVITY_STATUSES = {TERMINAL_ACTIVITY_STATUSES}\n\n"
    output += """@dataclass\nclass TSignedRequest:\n    \"\"\"A signed request ready to be sent to the Turnkey API.\"\"\"\n    \n    url: str\n    body: str\n    stamp: TStamp\n\n"""
    output += client_code

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        f.write(output)

    print(f"✅ Generated {OUTPUT_FILE}")
    print(f"   {len(swagger['paths'])} API methods")

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
        print("⚠️  ruff not found so skipping formatting")
        print("   Install with: pip install ruff")

    return 0


if __name__ == "__main__":
    sys.exit(main())
