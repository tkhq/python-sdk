"""Shared test fixtures and configuration."""

import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from turnkey_api_key_stamper import ApiKeyStamper, ApiKeyStamperConfig
from turnkey_http.generated.client import TurnkeyClient

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Turnkey test credentials from environment variables
API_PUBLIC_KEY = os.getenv("TURNKEY_API_PUBLIC_KEY")
API_PRIVATE_KEY = os.getenv("TURNKEY_API_PRIVATE_KEY")
ORG_ID = os.getenv("TURNKEY_ORGANIZATION_ID")
USER_ID = os.getenv("TURNKEY_USER_ID")
BASE_URL = os.getenv("TURNKEY_BASE_URL", "https://api.turnkey.com")


@pytest.fixture
def client():
    """Create a Turnkey client instance for testing."""
    config = ApiKeyStamperConfig(
        api_public_key=API_PUBLIC_KEY, api_private_key=API_PRIVATE_KEY
    )
    stamper = ApiKeyStamper(config)

    return TurnkeyClient(base_url=BASE_URL, stamper=stamper, organization_id=ORG_ID)


@pytest.fixture
def org_id():
    """Return the organization ID for assertions."""
    return ORG_ID


@pytest.fixture
def user_id():
    """Return a test user ID."""
    return USER_ID
