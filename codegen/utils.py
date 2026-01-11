"""Shared utilities for code generation from OpenAPI spec."""

import re
from typing import Dict, Any


def to_snake_case(name: str) -> str:
    """Convert camelCase to snake_case.

    Args:
        name: CamelCase or camelCase string

    Returns:
        snake_case string
    """
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def extract_latest_versions(definitions: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Extract the latest versions of definitions from OpenAPI spec.

    Args:
        definitions: Dictionary of OpenAPI definitions

    Returns:
        Dictionary mapping base names to their latest version info
    """
    latest_versions = {}
    key_version_regex = re.compile(r"^(v\d+)([A-Za-z0-9]+?)(V\d+)?$")

    for key in definitions.keys():
        match = key_version_regex.match(key)
        if match:
            full_name = match.group(0)
            base_name = match.group(2)
            version_suffix = match.group(3) or ""
            formatted_key_name = base_name[0].lower() + base_name[1:] + version_suffix

            if base_name not in latest_versions or version_suffix > latest_versions[
                base_name
            ].get("version_suffix", ""):
                latest_versions[base_name] = {
                    "full_name": full_name,
                    "formatted_key_name": formatted_key_name,
                    "version_suffix": version_suffix,
                }

    return latest_versions


def method_type_from_method_name(method_name: str) -> str:
    """Determine method type from method name.

    Args:
        method_name: The method name (e.g., "getWhoami", "tGetWhoami", "createPrivateKeys")

    Returns:
        Method type: "query", "activity", "activityDecision", or "noop"
    """
    method_name_lower = method_name.lower()

    if method_name in ["approveActivity", "rejectActivity"]:
        return "activityDecision"
    if method_name.startswith("nOOP"):
        return "noop"
    # Note: method names may have 't' prefix from types generation (e.g., "tGetWhoami")
    # or no prefix from HTTP generation (e.g., "getWhoami")
    if (
        method_name_lower.startswith("get")
        or method_name_lower.startswith("list")
        or method_name_lower.startswith("test")
        or method_name_lower.startswith("tget")
        or method_name_lower.startswith("tlist")
        or method_name_lower.startswith("ttest")
    ):
        return "query"
    return "activity"
