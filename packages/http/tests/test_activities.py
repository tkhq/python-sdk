"""Test Turnkey HTTP client activity methods"""

import pytest
import secrets
from turnkey_sdk_types import (
    v1ApiKeyParamsV2,
    v1ApiKeyCurve,
    CreateApiKeysBody,
    CreateApiKeysResponse,
    TurnkeyNetworkError,
)


def test_create_api_keys(client, user_id):
    """Test createApiKeys command method."""
    print("🔧 Testing createApiKeys")

    # Generate a new key pair for the API key
    private_key = secrets.token_bytes(32)
    # For P256, derive public key (simplified - in production use proper crypto library)
    public_key = private_key.hex()

    # Create the API key parameters
    api_key = v1ApiKeyParamsV2(
        apiKeyName="Test API Key from Python SDK",
        publicKey=f"02{public_key[:64]}",  # Compressed public key format
        curveType=v1ApiKeyCurve.API_KEY_CURVE_P256,
        expirationSeconds="3600",  # 1 hour
    )

    # Create the typed request
    request = CreateApiKeysBody(userId=user_id, apiKeys=[api_key])

    # Make the createApiKeys request with typed input
    response = client.create_api_keys(request)

    # Assertions
    assert response is not None
    assert response.activity is not None
    assert response.activity.id is not None
    assert response.activity.status in [
        "ACTIVITY_STATUS_COMPLETED",
        "ACTIVITY_STATUS_PENDING",
        "ACTIVITY_STATUS_CONSENSUS_NEEDED",
    ]

    print("✅ createApiKeys request successful!")
    print("\nActivity:")
    print(f"  Activity ID: {response.activity.id}")
    print(f"  Status: {response.activity.status}")
    print(f"  Type: {response.activity.type}")

    # Check if apiKeyIds were flattened into response
    if hasattr(response, "apiKeyIds") and response.apiKeyIds:
        print(f"  Created API Key IDs: {response.apiKeyIds}")


def test_organization_id_override(client, user_id):
    """Test that organizationId in request body overrides client config."""
    print("🔧 Testing organizationId override")

    # Generate a new key pair for the API key
    private_key = secrets.token_bytes(32)
    public_key = private_key.hex()

    # Create the API key parameters
    api_key = v1ApiKeyParamsV2(
        apiKeyName="Test API Key - Should Fail",
        publicKey=f"02{public_key[:64]}",
        curveType=v1ApiKeyCurve.API_KEY_CURVE_P256,
        expirationSeconds="3600",
    )

    # Create request with WRONG organization ID to prove override works
    wrong_org_id = "00000000-0000-0000-0000-000000000000"
    request = CreateApiKeysBody(
        organizationId=wrong_org_id,  # Override with wrong org ID
        userId=user_id,
        apiKeys=[api_key],
    )

    # This should fail because we're using a wrong organization ID
    with pytest.raises(TurnkeyNetworkError) as exc_info:
        client.create_api_keys(request)

    # Verify the error is related to the wrong organization
    error = exc_info.value
    error_msg = str(error)
    print(f"\n❌ Error message: {error_msg}")
    print(f"   Status code: {error.status_code}")
    print(f"✅ Request failed as expected with wrong organization ID")

    # Assert that we got the expected error for organization not found
    assert "no organization found" in error_msg.lower()
    assert wrong_org_id in error_msg


def test_stamp_create_api_keys_send_signed_request(client, user_id):
    """Stamp an activity and submit via send_signed_request."""
    print("\n🔧 Testing stamp + send for createApiKeys")

    private_key = secrets.token_bytes(32)
    public_key = private_key.hex()

    api_key = v1ApiKeyParamsV2(
        apiKeyName="Test API Key via Stamp",
        publicKey=f"02{public_key[:64]}",
        curveType=v1ApiKeyCurve.API_KEY_CURVE_P256,
        expirationSeconds="3600",
    )

    request = CreateApiKeysBody(userId=user_id, apiKeys=[api_key])

    # Stamp only (do not auto-send)
    signed_req = client.stamp_create_api_keys(request)

    # Send stamped request via client with type (includes polling)
    resp = client.send_signed_request(signed_req, CreateApiKeysResponse)

    assert resp is not None
    assert resp.activity is not None
    assert resp.activity.id is not None
    assert resp.apiKeyIds is not None
    assert isinstance(resp.apiKeyIds, list)
    print(
        f"✅ Stamped createApiKeys submitted; activity {resp.activity.id} apiKeyIds: {resp.apiKeyIds}"
    )
