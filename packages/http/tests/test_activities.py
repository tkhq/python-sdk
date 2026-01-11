"""Test Turnkey HTTP client command methods (activities)."""

import pytest
import secrets
from turnkey_sdk_types.generated.types import (
    v1ApiKeyParamsV2,
    v1ApiKeyCurve,
    v1CreateApiKeysIntentV2
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
        expirationSeconds="3600"  # 1 hour
    )
    
    # Create the typed request
    request = v1CreateApiKeysIntentV2(
        userId=user_id,
        apiKeys=[api_key]
    )
    
    # Make the createApiKeys request with typed input
    response = client.create_api_keys(request)
    
    # Assertions
    assert response is not None
    assert response.activity is not None
    assert response.activity.id is not None
    assert response.activity.status in [
        "ACTIVITY_STATUS_COMPLETED",
        "ACTIVITY_STATUS_PENDING",
        "ACTIVITY_STATUS_CONSENSUS_NEEDED"
    ]
    
    print("✅ createApiKeys request successful!")
    print("\nActivity:")
    print(f"  Activity ID: {response.activity.id}")
    print(f"  Status: {response.activity.status}")
    print(f"  Type: {response.activity.type}")
    
    # Check if apiKeyIds were flattened into response
    if hasattr(response, 'apiKeyIds') and response.apiKeyIds:
        print(f"  Created API Key IDs: {response.apiKeyIds}")
