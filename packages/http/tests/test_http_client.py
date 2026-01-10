"""Test the Turnkey HTTP client with a getWhoami request."""

from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
from turnkey_http.generated.client import TurnkeyClient

# Turnkey goodies
API_PUBLIC_KEY = "0260e1e5aa1be0971d891b8cb5b70d685646fe95f5be1f8b935baa689a0819e10c"
API_PRIVATE_KEY = "49c4dc1ccbe1eb6a3d4670bfd671e8a193ca3d32b42be7ff00eb2d964d01e632"
ORG_ID = "3516d5dd-4245-42b6-baaa-6212451db535"
BASE_URL = "https://api.turnkey.com"


def test_get_whoami():
    print("🔧 Testing Turnkey HTTP Client - getWhoami")
    
    # we initialize the stamper
    config = ApiKeyStamperConfig(
        api_public_key=API_PUBLIC_KEY,
        api_private_key=API_PRIVATE_KEY
    )
    stamper = ApiKeyStamper(config)
    
    # we create the HTTP client with the stamper
    client = TurnkeyClient(
        base_url=BASE_URL,
        stamper=stamper,
        organization_id=ORG_ID
    )
    
    # make the getWhoami request
    response = client.get_whoami()
    
    # Assertions
    assert response is not None
    assert "organizationId" in response
    assert response["organizationId"] == ORG_ID
    assert "userId" in response
    assert "username" in response
    
    print("✅ Request successful!")
    print("\nResponse:")
    print(f"  Organization ID: {response.get('organizationId')}")
    print(f"  Organization Name: {response.get('organizationName')}")
    print(f"  User ID: {response.get('userId')}")
    print(f"  Username: {response.get('username')}")


if __name__ == "__main__":
    test_get_whoami()
