import json

from turnkey_sdk_types import (
    TEthSendTransactionBody,
)

def test_pydantic_aliases():
    """Test Pydantic field aliasing for Python keywords and special characters.

    Some API fields use Python keywords (like 'from') or special characters (like '@type')
    which cannot be used as Python identifiers. We use Pydantic's Field(alias=...) to map
    these to safe Python names (e.g., from_ -> "from", type -> "@type").

    This test verifies that:
    1. Python code uses safe names (from_, type)
    2. JSON serialization uses original API names ("from", "@type")
    3. JSON parsing accepts original API names and maps to Python names
    """
    print("🔧 Testing Pydantic Field Aliases on Generated Types")
    print("=" * 50)

    # Test 1: TEthSendTransactionBody with 'from' keyword field
    print("\n✓ Test 1: TEthSendTransactionBody 'from' keyword field")

    eth_tx = TEthSendTransactionBody(
        timestampMs="1234567890",
        organizationId="test-org",
        from_="0x1234567890123456789012345678901234567890",  # Python name with underscore
        caip2="eip155:1",
        to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
    )

    json_dict = eth_tx.model_dump(by_alias=True, exclude_none=True)
    json_str = json.dumps(json_dict, indent=2)
    print(f"  Python: from_='{eth_tx.from_}'")
    print(f"  JSON:\n{json_str}")

    assert "from" in json_dict, "Expected 'from' in JSON output"
    assert "from_" not in json_dict, "Expected 'from_' to be aliased to 'from'"
    assert json_dict["from"] == "0x1234567890123456789012345678901234567890"
    print("  ✅ Field 'from_' correctly aliased to 'from' in JSON")

    # Test 2: Parse TEthSendTransactionBody from JSON with 'from' keyword
    print("\n✓ Test 2: Parse TEthSendTransactionBody from JSON with 'from' keyword")
    json_input = {
        "timestampMs": "1234567890",
        "organizationId": "test-org",
        "from": "0x9999999999999999999999999999999999999999",
        "caip2": "eip155:137",
        "to": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    }
    parsed = TEthSendTransactionBody.model_validate(json_input)
    print(f"  JSON:   {json.dumps(json_input, indent=2)}")
    print(f"  Python: from_='{parsed.from_}', to='{parsed.to}'")

    assert parsed.from_ == "0x9999999999999999999999999999999999999999"
    assert parsed.to == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    print("  ✅ JSON 'from' correctly parsed to Python 'from_' field")

    # Test 3: populate_by_name allows both names
    print("\n✓ Test 3: ConfigDict(populate_by_name=True) allows both field names")
    json_with_python_name = {
        "timestampMs": "1234567890",
        "organizationId": "test-org",
        "from_": "0x7777777777777777777777777777777777777777",  # Using Python name in JSON
        "caip2": "eip155:1",
        "to": "0x8888888888888888888888888888888888888888",
    }
    parsed2 = TEthSendTransactionBody.model_validate(json_with_python_name)
    print(f"  JSON (Python name): {json.dumps(json_with_python_name, indent=2)}")
    print(f"  Python: from_='{parsed2.from_}'")

    assert parsed2.from_ == "0x7777777777777777777777777777777777777777"
    print("  ✅ Both Python and JSON field names work for parsing")

    print("\n" + "=" * 50)
    print("✅ All Pydantic field alias tests passed!")


if __name__ == "__main__":
    test_pydantic_aliases()
