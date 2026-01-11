"""Test Turnkey HTTP client query methods."""


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
