#!/usr/bin/env python3
"""Generate HTTP client from OpenAPI specification."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

# Add codegen directory to Python path
CODEGEN_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CODEGEN_DIR))

from constants import (
    COMMENT_HEADER,
    METHODS_WITH_ONLY_OPTIONAL_PARAMETERS,
    TERMINAL_ACTIVITY_STATUSES,
)
from utils import (
    to_snake_case,
    extract_latest_versions,
    method_type_from_method_name,
    resolve_versioned_activity_type,
    get_versioned_result_type,
)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema" / "public_api.swagger.json"
OUTPUT_DIR = PROJECT_ROOT / "packages" / "http" / "src" / "turnkey_http" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "client.py"


def get_request_activity_type(
    definitions: Dict[str, Any], operation: Dict[str, Any]
) -> str | None:
    """Return the activity type from the request definition's "type" enum, if any."""
    for param in operation.get("parameters", []):
        if param.get("in") == "body" and "$ref" in param.get("schema", {}):
            request_type_name = param["schema"]["$ref"].replace("#/definitions/", "")
            request_def = definitions.get(request_type_name, {})
            enum = request_def.get("properties", {}).get("type", {}).get("enum")
            if enum:
                return enum[0]
    return None


VERSIONS_FILE = PROJECT_ROOT / "codegen" / "activity_versions.json"

# Filled while generating: snake_case method name -> activity type the client sends.
SENT_ACTIVITY_TYPES: Dict[str, str] = {}


def check_activity_versions(sent: Dict[str, str]) -> None:
    """Fail when a method's sent activity type differs from codegen/activity_versions.json.

    A regen takes unpinned activity versions from the schema, so a new schema can move a
    method to a new version with only a one-line change buried in client.py. This makes
    every such move a visible diff in the snapshot. Set CODEGEN_ACCEPT_VERSION_CHANGES=1
    to rewrite the snapshot after reviewing the moves.
    """
    import os

    previous: Dict[str, str] = {}
    if VERSIONS_FILE.exists():
        previous = json.loads(VERSIONS_FILE.read_text())
    moved = {
        name: (previous.get(name), sent[name])
        for name in sorted(sent)
        if previous.get(name) != sent[name]
    }
    if not moved and VERSIONS_FILE.exists():
        return
    if (
        moved
        and VERSIONS_FILE.exists()
        and not os.environ.get("CODEGEN_ACCEPT_VERSION_CHANGES")
    ):
        lines = [
            f"  {name}: {old or '(new)'} -> {new}" for name, (old, new) in moved.items()
        ]
        raise SystemExit(
            "Activity versions changed for these methods:\n"
            + "\n".join(lines)
            + "\nPin them in codegen/constants.py to keep the old version, or list the moves "
            "in the PR and rerun with CODEGEN_ACCEPT_VERSION_CHANGES=1 to update "
            f"{VERSIONS_FILE.name}."
        )
    VERSIONS_FILE.write_text(json.dumps(dict(sorted(sent.items())), indent=2) + "\n")
    print(f"📝 Updated {VERSIONS_FILE} ({len(moved)} change(s))")


def generate_sdk_client(swagger: Dict[str, Any]) -> str:
    """Generate the SDK client from Swagger spec."""
    namespace = next(
        (tag["name"] for tag in swagger.get("tags", []) if "name" in tag), None
    )
    code_buffer = []
    latest_versions = extract_latest_versions(swagger["definitions"])

    # Generate class header
    code_buffer.append("""
@dataclass
class PollingConfig:
    \"\"\"Interval and timeout for an optional approval poll.
    
    Both values are milliseconds. Pass one as ``mfa_polling`` or
    ``consensus_polling``. The poll stays off when the config is omitted, or
    when either value is ``0``. The MFA poll doubles its interval on each
    attempt, up to 5 seconds. The consensus poll keeps this interval.
    \"\"\"
    
    interval_ms: int
    timeout_ms: int


class TurnkeyClient:
    \"\"\"Turnkey API HTTP client with auto-generated methods.\"\"\"
    
    def __init__(
        self,
        base_url: str,
        stamper: ApiKeyStamper,
        organization_id: str,
        default_timeout: int = 30,
        polling_interval_ms: int = 1000,
        max_polling_retries: int = 10,
        mfa_polling: Optional[PollingConfig] = None,
        consensus_polling: Optional[PollingConfig] = None,
    ):
        \"\"\"Initialize the Turnkey client.
        
        Args:
            base_url: Base URL for the Turnkey API
            stamper: API key stamper for authentication
            organization_id: Organization ID
            default_timeout: Default request timeout in seconds
            polling_interval_ms: Polling interval for activity status in milliseconds
            max_polling_retries: Maximum number of polling retries
            mfa_polling: Optional authenticators-needed poll. Omit it to raise
                TurnkeyActivityAuthenticatorsNeededError immediately.
            consensus_polling: Optional consensus-needed poll. Omit it to raise
                TurnkeyActivityConsensusNeededError immediately.
        \"\"\"
        self.base_url = base_url.rstrip("/")
        self.stamper = stamper
        self.organization_id = organization_id
        self.default_timeout = default_timeout
        self.polling_interval_ms = polling_interval_ms
        self.max_polling_retries = max_polling_retries
        self.mfa_polling = mfa_polling
        self.consensus_polling = consensus_polling
    
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
    
    def _poll_body(self, activity: Any) -> GetActivityBody:
        \"\"\"Build the get_activity body to poll an activity in its own organization.
        
        Args:
            activity: Activity object with id and organizationId attributes.
            
        Returns:
            GetActivityBody for the activity's organization. Falls back to the
            client's default organization if the activity has none.
        \"\"\"
        organization_id = getattr(activity, "organizationId", None) or self.organization_id
        return GetActivityBody(organizationId=organization_id, activityId=activity.id)
    
    def _poll_for_completion(self, activity: Any) -> Any:
        \"\"\"Poll until activity reaches terminal status.
        
        Args:
            activity: Initial activity object with id and status attributes.
            
        Returns:
            Activity object after reaching terminal status or max retries.
        \"\"\"
        if activity.status in TERMINAL_ACTIVITY_STATUSES:
            return activity
        
        attempts = 0
        while attempts < self.max_polling_retries:
            time.sleep(self.polling_interval_ms / 1000.0)
            poll_response = self.get_activity(self._poll_body(activity))
            activity = poll_response.activity
            if activity.status in TERMINAL_ACTIVITY_STATUSES:
                break
            attempts += 1
        
        return activity
    
    def _raise_for_activity_status(self, activity: Any) -> None:
        \"\"\"Raise a typed error if an activity did not complete.
        
        Args:
            activity: Activity object after polling.
            
        Raises:
            TurnkeyActivityConsensusNeededError: If the activity needs more approvals.
            TurnkeyActivityAuthenticatorsNeededError: If the activity needs authenticator
                approval.
            TurnkeyActivityError: If the activity failed, was rejected, or polling
                stopped before it reached a terminal status.
        \"\"\"
        status = getattr(activity.status, "value", activity.status)
        if status == "ACTIVITY_STATUS_COMPLETED":
            return
        
        activity_type = getattr(activity.type, "value", activity.type)
        failure = getattr(activity, "failure", None)
        failure_message = getattr(failure, "message", None) if failure else None
        
        if status == "ACTIVITY_STATUS_CONSENSUS_NEEDED":
            raise TurnkeyActivityConsensusNeededError(
                f"Consensus needed for activity {activity.id}",
                activity_id=activity.id,
                activity_status=status,
                activity_type=activity_type,
                failure=failure_message,
            )
        
        if status == "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED":
            raise TurnkeyActivityAuthenticatorsNeededError(
                f"Authenticators needed for activity {activity.id}",
                activity_id=activity.id,
                activity_status=status,
                activity_type=activity_type,
                failure=failure_message,
            )
        
        if status == "ACTIVITY_STATUS_FAILED":
            message = f"Activity {activity.id} failed"
        elif status == "ACTIVITY_STATUS_REJECTED":
            message = f"Activity {activity.id} was rejected"
        elif status in TERMINAL_ACTIVITY_STATUSES:
            message = f"Activity {activity.id} ended with status {status}"
        else:
            message = f"Activity {activity.id} did not reach a terminal status after polling"
        
        raise TurnkeyActivityError(
            message,
            activity_id=activity.id,
            activity_status=status,
            activity_type=activity_type,
            failure=failure_message,
        )
    
    def _poll_while_status(
        self,
        activity: Any,
        watched_status: str,
        interval_ms: int,
        timeout_ms: int,
        backoff: bool,
    ) -> Any:
        \"\"\"Poll while an activity stays in one approval status.
        
        Disabled unless interval and timeout are both greater than zero. If the
        timeout is reached first, the latest activity is returned so the caller can
        raise. If the status changes, normal activity polling resumes. A later
        approval status is not handed to the other approval poll.
        
        Args:
            activity: Activity already in ``watched_status``.
            watched_status: Status to keep polling.
            interval_ms: Delay before each fetch, in milliseconds.
            timeout_ms: How long to keep polling, in milliseconds.
            backoff: When true, double the delay each attempt, up to 5 seconds.
            
        Returns:
            The latest activity.
        \"\"\"
        status = getattr(activity.status, "value", activity.status)
        if status != watched_status:
            return activity
        if interval_ms <= 0 or timeout_ms <= 0:
            return activity
        
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        delay_ms = interval_ms
        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                return activity
            
            time.sleep(min(delay_ms / 1000.0, remaining_s))
            if time.monotonic() >= deadline:
                return activity
            
            poll_response = self.get_activity(self._poll_body(activity))
            activity = poll_response.activity
            status = getattr(activity.status, "value", activity.status)
            if status != watched_status:
                return self._poll_for_completion(activity)
            
            if backoff:
                delay_ms = min(delay_ms * 2, 5000)
    
    def _poll_mfa(self, activity: Any) -> Any:
        \"\"\"Poll an authenticators-needed activity on its own interval and timeout.\"\"\"
        interval_ms, timeout_ms = self._polling_bounds(self.mfa_polling)
        return self._poll_while_status(
            activity,
            "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED",
            interval_ms,
            timeout_ms,
            True,
        )
    
    def _poll_consensus(self, activity: Any) -> Any:
        \"\"\"Poll a consensus-needed activity on its own interval and timeout.\"\"\"
        interval_ms, timeout_ms = self._polling_bounds(self.consensus_polling)
        return self._poll_while_status(
            activity,
            "ACTIVITY_STATUS_CONSENSUS_NEEDED",
            interval_ms,
            timeout_ms,
            False,
        )
    
    def _polling_bounds(self, polling: Optional[PollingConfig]) -> tuple[int, int]:
        \"\"\"Return an interval and timeout, or zeros when the poll is off.\"\"\"
        if polling is None:
            return 0, 0
        return polling.interval_ms, polling.timeout_ms
    
    def _poll_approval_if_needed(self, activity: Any) -> Any:
        \"\"\"Run the consensus or MFA poll once, when that poll is enabled.\"\"\"
        status = getattr(activity.status, "value", activity.status)
        if status == "ACTIVITY_STATUS_CONSENSUS_NEEDED":
            return self._poll_consensus(activity)
        if status == "ACTIVITY_STATUS_AUTHENTICATORS_NEEDED":
            return self._poll_mfa(activity)
        return activity
    
    def _activity(self, url: str, body: Dict[str, Any], result_key: str, response_type: type) -> Any:
        \"\"\"Execute an activity and poll for completion.
        
        Args:
            url: Endpoint URL
            body: Request body
            result_key: Key to extract result from activity when completed
            response_type: Pydantic model class for response parsing
            
        Returns:
            Parsed response as Pydantic model with flattened result fields
            
        Raises:
            TurnkeyActivityConsensusNeededError: If the activity needs more approvals.
            TurnkeyActivityAuthenticatorsNeededError: If the activity needs authenticator
                approval.
            TurnkeyActivityError: If the activity did not complete, or completed
                without the expected result.
            TurnkeyNetworkError: If a request fails.
        \"\"\"
        # Make initial request, we parse as activity response without result fields
        initial_response = self._request(url, body, GetActivityResponse)
        
        # Poll for completion. Consensus and authenticators each have their own poll.
        activity = self._poll_for_completion(initial_response.activity)
        activity = self._poll_approval_if_needed(activity)
        self._raise_for_activity_status(activity)
        
        # Get the versioned result (e.g., 'createApiKeysResultV2') and flatten its fields into the response
        result_data = getattr(activity.result, result_key, None) if activity.result else None
        if result_data is None:
            raise TurnkeyActivityError(
                f"Activity {activity.id} completed without a {result_key} result",
                activity_id=activity.id,
                activity_status=getattr(activity.status, "value", activity.status),
                activity_type=getattr(activity.type, "value", activity.type),
                code=TurnkeyErrorCodes.ACTIVITY_RESULT_MISSING,
            )
        
        result_dict = result_data.model_dump(by_alias=True, exclude_none=True)
        return response_type(activity=activity, **result_dict)
    
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

    @overload
    def send_signed_request(self, signed_request: SignedRequest, response_type: type[T]) -> T: ...
    
    @overload
    def send_signed_request(self, signed_request: SignedRequest) -> Any: ...
    
    def send_signed_request(self, signed_request: SignedRequest, response_type: type[T] | None = None) -> Any:
        \"\"\"Submit a signed request and poll for activity completion if needed.
        
        You can pass in the SignedRequest returned by any of the SDK's
        stamping methods (stamp_create_api_keys, stamp_get_policies, etc.).
        
        For activities, this will poll until the activity reaches a terminal status.
        If response_type is given and the activity does not complete, this raises
        TurnkeyActivityError. Without response_type, it returns the raw payload
        for every status so the caller can inspect the activity.
        
        Args:
            signed_request: A SignedRequest object returned by a stamping method.
            response_type: Optional callable to convert the JSON payload to a typed value.
                          Typically a Pydantic model class.
            
        Returns:
            The parsed response via response_type, or raw JSON dict if no type provided.
            
        Raises:
            TurnkeyActivityConsensusNeededError: If the activity needs more approvals.
            TurnkeyActivityAuthenticatorsNeededError: If the activity needs authenticator
                approval.
            TurnkeyActivityError: If response_type is given and the activity did not complete.
            TurnkeyNetworkError: If the request fails.
        \"\"\"
        headers = {
            signed_request.stamp.stamp_header_name: signed_request.stamp.stamp_header_value,
            "Content-Type": "application/json",
            "X-Client-Version": VERSION,
        }
        
        try:
            response = requests.post(
                signed_request.url,
                headers=headers,
                data=signed_request.body,
                timeout=self.default_timeout
            )
        except requests.RequestException as exc:
            raise TurnkeyNetworkError(
                "Signed request failed",
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
        
        payload = response.json()
        
        # Poll for activity completion if this is an activity request
        if signed_request.type == RequestType.ACTIVITY:
            activity_response = GetActivityResponse(**payload)
            activity = self._poll_for_completion(activity_response.activity)
            activity = self._poll_approval_if_needed(activity)
            
            # Update payload with polled activity
            activity_dict = activity.model_dump(by_alias=True, exclude_none=True) if hasattr(activity, 'model_dump') else {}
            payload["activity"] = activity_dict
            
            # Typed callers get an error if the activity did not complete.
            # Without a response_type, return the raw payload for every status.
            if response_type is not None:
                self._raise_for_activity_status(activity)
            
            # Flatten the result that is set (e.g., createPolicyResult, createSubOrganizationResultV7)
            result = activity.result
            if activity.status == "ACTIVITY_STATUS_COMPLETED" and result is not None:
                for field_name in type(result).model_fields:
                    result_data = getattr(result, field_name, None)
                    if result_data is not None:
                        payload.update(result_data.model_dump(by_alias=True, exclude_none=True))
                        break
        
        return response_type(**payload) if response_type is not None else payload
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

        input_type = f"{operation_name_without_namespace}Body"
        response_type = f"{operation_name_without_namespace}Response"

        unversioned_activity_type = (
            f"ACTIVITY_TYPE_{to_snake_case(operation_name_without_namespace).upper()}"
        )
        versioned_activity_type = resolve_versioned_activity_type(
            unversioned_activity_type
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
    
    def stamp_{snake_method_name}(self, input: Optional[{input_type}] = None) -> SignedRequest:
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
        
        return SignedRequest(url=full_url, body=body_str, stamp=stamp, type=RequestType.QUERY)
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
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> SignedRequest:
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
        
        return SignedRequest(url=full_url, body=body_str, stamp=stamp, type=RequestType.QUERY)
""")

        elif method_type == "activity":
            # Use the activity type from the request definition. A pinned
            # version in VERSIONED_ACTIVITY_TYPES takes precedence.
            schema_activity_type = get_request_activity_type(
                swagger["definitions"], operation
            )
            if schema_activity_type:
                unversioned_activity_type = re.sub(r"_V\d+$", "", schema_activity_type)
                pinned_activity_type = resolve_versioned_activity_type(
                    unversioned_activity_type
                )
                versioned_activity_type = (
                    pinned_activity_type
                    if pinned_activity_type != unversioned_activity_type
                    else schema_activity_type
                )

            SENT_ACTIVITY_TYPES[snake_method_name] = versioned_activity_type

            # Use the pinned result type if there is one, else the latest version
            pinned_result_type = get_versioned_result_type(unversioned_activity_type)
            if pinned_result_type and pinned_result_type in swagger["definitions"]:
                pinned_result_key = re.sub(r"^v\d+", "", pinned_result_type)
                versioned_method_name = (
                    pinned_result_key[0].lower() + pinned_result_key[1:]
                )
            else:
                result_key = operation_name_without_namespace + "Result"
                versioned_method_name = latest_versions[result_key][
                    "formatted_key_name"
                ]

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
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> SignedRequest:
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
        
        return SignedRequest(url=full_url, body=body_str, stamp=stamp, type=RequestType.ACTIVITY)
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
    
    def stamp_{snake_method_name}(self, input: {input_type}) -> SignedRequest:
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
        
        return SignedRequest(url=full_url, body=body_str, stamp=stamp, type=RequestType.ACTIVITY_DECISION)
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
    output += "import json\nimport time\nfrom dataclasses import dataclass\nfrom typing import Any, Callable, Dict, Optional, TypeVar, overload\nimport requests\n"
    output += "from turnkey_api_key_stamper import ApiKeyStamper\n"
    output += "from turnkey_sdk_types import *\n"
    output += "from ..version import VERSION\n\n"
    output += "T = TypeVar('T')\n\n"
    output += f"TERMINAL_ACTIVITY_STATUSES = {TERMINAL_ACTIVITY_STATUSES}\n\n"
    output += client_code

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write output
    check_activity_versions(SENT_ACTIVITY_TYPES)

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
