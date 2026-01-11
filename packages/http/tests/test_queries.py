"""Test Turnkey HTTP client query methods"""

from turnkey_http.utils import send_signed_request
from turnkey_sdk_types import (
    TGetOrganizationResponse,
    TGetOrganizationBody,
    TurnkeyNetworkError,
)

import pytest


def test_get_whoami(client, org_id):
    """Test getWhoami query method."""
    print("🔧 Testing getWhoami")

    response = client.get_whoami()

    # Assertions
    assert response is not None
    assert response.organizationId == org_id
    assert response.userId is not None
    assert response.username is not None

    print("✅ getWhoami successful!")
    print("\nResponse:")
    print(f"  Organization ID: {response.organizationId}")
    print(f"  Organization Name: {response.organizationName}")
    print(f"  User ID: {response.userId}")
    print(f"  Username: {response.username}")


def test_get_organization(client, org_id):
    """Test getOrganization query method."""
    print("\n🔧 Testing getOrganization")

    response = client.get_organization()

    # Assertions
    assert response is not None
    assert response.organizationData is not None
    assert response.organizationData.organizationId == org_id
    assert response.organizationData.name is not None

    print("✅ getOrganization successful!")
    print("\nOrganization:")
    print(f"  ID: {response.organizationData.organizationId}")
    print(f"  Name: {response.organizationData.name}")


def test_get_users(client):
    """Test getUsers (list) query method."""
    print("\n🔧 Testing getUsers")

    response = client.get_users()

    # Assertions
    assert response is not None
    assert response.users is not None
    assert isinstance(response.users, list)

    print("✅ getUsers successful!")
    print(f"\nFound {len(response.users)} users")
    if response.users:
        first_user = response.users[0]
        print(f"  First user: {first_user.userName} ({first_user.userId})")


def test_get_wallets(client):
    """Test getWallets (list) query method."""
    print("\n🔧 Testing getWallets")

    response = client.get_wallets()

    # Assertions
    assert response is not None
    assert response.wallets is not None
    assert isinstance(response.wallets, list)

    print("✅ getWallets successful!")
    print(f"\nFound {len(response.wallets)} wallets")


def test_stamp_get_organization_send_signed_request(client, org_id):
    """Stamp a query and submit via send_signed_request."""
    print("\n🔧 Testing stamp + send for getOrganization")

    # Stamp only (queries have flat bodies)
    signed_req = client.stamp_get_organization(TGetOrganizationBody())

    # Manually send stamped request; parse into typed response
    org_resp = send_signed_request(
        signed_req, parser=lambda p: TGetOrganizationResponse(**p)
    )

    assert org_resp is not None
    assert org_resp.organizationData is not None
    assert org_resp.organizationData.organizationId == org_id
    print(
        f"✅ Stamped getOrganization submitted; org: {org_resp.organizationData.organizationId}"
    )


def test_organization_id_override_query(client):
    """Test that organizationId in request body overrides client config for queries."""
    print("\n🔧 Testing organizationId override for queries")

    # Create request with WRONG organization ID to prove override works
    wrong_org_id = "00000000-0000-0000-0000-000000000000"
    request = TGetOrganizationBody(organizationId=wrong_org_id)

    # This should fail because we're using a wrong organization ID
    with pytest.raises(TurnkeyNetworkError) as exc_info:
        client.get_organization(request)

    # Verify the error is related to the wrong organization
    error = exc_info.value
    error_msg = str(error)
    print(f"\n❌ Error message: {error_msg}")
    print(f"   Status code: {error.status_code}")
    print(f"✅ Request failed as expected with wrong organization ID")

    # Assert that we got an error for invalid organization (different error than activities)
    assert "invalid organization ID" in error_msg
