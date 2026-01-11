"""Helper functions for Pydantic model generation."""

import keyword
from typing import Dict, Any, Tuple


def needs_field_alias(prop: str) -> Tuple[bool, str]:
    """Check if property needs a Field alias and return (needs_alias, original_name)."""
    # Check for @ prefix
    if prop.startswith("@"):
        return True, prop

    # Check for Python keywords
    if keyword.iskeyword(prop):
        return True, prop

    # Check for invalid identifiers
    if not prop.isidentifier():
        return True, prop

    return False, prop


def safe_property_name(name: str) -> str:
    """Convert a property name to a safe Python identifier."""
    # If it starts with @, remove it
    if name.startswith("@"):
        name = name[1:]

    # If it's a Python keyword, append underscore
    if keyword.iskeyword(name):
        return name + "_"

    # If it's not a valid identifier, try to make it one
    if not name.isidentifier():
        # Replace invalid chars with underscore
        import re

        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # If it starts with a digit, prepend underscore
        if name and name[0].isdigit():
            name = "_" + name

    return name
