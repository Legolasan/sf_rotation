"""
Shared pytest fixtures and configuration for sf-rotation tests.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires real Snowflake/Hevo credentials)"
    )


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires real credentials)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is specified."""
    if config.getoption("--run-integration"):
        return
    
    skip_integration = pytest.mark.skip(reason="Need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_private_key():
    """Sample RSA private key for testing."""
    return """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3q32ijwJFklXU
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
-----END PRIVATE KEY-----"""


@pytest.fixture
def sample_public_key():
    """Sample RSA public key for testing."""
    return """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt6t9oo8CRZJVlHZ5DDDD
DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD
DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD
DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDAAA
-----END PUBLIC KEY-----"""


@pytest.fixture
def sample_formatted_public_key():
    """Public key formatted for Snowflake (no headers, single line)."""
    return "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt6t9oo8CRZJV..."


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Sample configuration dictionary for testing."""
    return {
        'snowflake': {
            'account_url': 'test-account.us-west-2.snowflakecomputing.com',
            'username': 'test_user',
            'password': 'test_password',
            'warehouse': 'TEST_WAREHOUSE',
            'database': 'TEST_DATABASE',
            'user_to_modify': 'service_user',
            'region': 'us-west-2'
        },
        'hevo': {
            'base_url': 'https://us.hevodata.com',
            'username': 'hevo_user',
            'password': 'hevo_password',
            'destination_id': '12345',
            'destination_name': 'test_destination'
        },
        'keys': {
            'encrypted': False,
            'passphrase': '',
            'output_directory': './keys'
        }
    }


@pytest.fixture
def sample_config_v2() -> Dict[str, Any]:
    """Sample configuration for v2.0 API testing."""
    return {
        'snowflake': {
            'account_url': 'test-account.us-west-2.snowflakecomputing.com',
            'username': 'test_user',
            'password': 'test_password',
            'warehouse': 'TEST_WAREHOUSE',
            'database': 'TEST_DATABASE',
            'user_to_modify': 'service_user',
            'region': 'us-west-2'
        },
        'hevo': {
            'base_url': 'https://s-walrus.hevo.me',
            'username': 'hevo_user',
            'password': 'hevo_password',
            'destination_id': '1',
            'destination_name': 'test_destination'
        },
        'keys': {
            'encrypted': False,
            'passphrase': '',
            'output_directory': './keys'
        }
    }


@pytest.fixture
def sample_config_no_destination_id() -> Dict[str, Any]:
    """Sample configuration without destination_id."""
    return {
        'snowflake': {
            'account_url': 'test-account.snowflakecomputing.com',
            'username': 'test_user',
            'password': 'test_password',
            'warehouse': 'TEST_WAREHOUSE',
            'database': 'TEST_DATABASE',
            'user_to_modify': 'service_user'
        },
        'hevo': {
            'base_url': 'https://us.hevodata.com',
            'username': 'hevo_user',
            'password': 'hevo_password',
            'destination_id': '',  # Empty
            'destination_name': 'test_destination'
        },
        'keys': {
            'encrypted': False,
            'passphrase': '',
            'output_directory': './keys'
        }
    }


# =============================================================================
# Mock Fixtures for Snowflake
# =============================================================================

@pytest.fixture
def mock_snowflake_connection():
    """Mock Snowflake connection context manager."""
    with patch('snowflake.connector.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        yield {
            'connect': mock_connect,
            'connection': mock_conn,
            'cursor': mock_cursor
        }


@pytest.fixture
def mock_snowflake_user_keys_slot1_only():
    """Mock user with only RSA_PUBLIC_KEY set (slot 1)."""
    return [
        ('RSA_PUBLIC_KEY', 'MIIBIjAN...'),
        ('RSA_PUBLIC_KEY_FP', 'SHA256:abc123...'),
        ('RSA_PUBLIC_KEY_2', None),
        ('RSA_PUBLIC_KEY_2_FP', None),
    ]


@pytest.fixture
def mock_snowflake_user_keys_slot2_only():
    """Mock user with only RSA_PUBLIC_KEY_2 set (slot 2)."""
    return [
        ('RSA_PUBLIC_KEY', None),
        ('RSA_PUBLIC_KEY_FP', None),
        ('RSA_PUBLIC_KEY_2', 'MIIBIjAN...'),
        ('RSA_PUBLIC_KEY_2_FP', 'SHA256:def456...'),
    ]


@pytest.fixture
def mock_snowflake_user_keys_both_slots():
    """Mock user with both key slots occupied."""
    return [
        ('RSA_PUBLIC_KEY', 'MIIBIjAN...'),
        ('RSA_PUBLIC_KEY_FP', 'SHA256:abc123...'),
        ('RSA_PUBLIC_KEY_2', 'MIIBIjAN...'),
        ('RSA_PUBLIC_KEY_2_FP', 'SHA256:def456...'),
    ]


@pytest.fixture
def mock_snowflake_user_keys_no_keys():
    """Mock user with no keys set."""
    return [
        ('RSA_PUBLIC_KEY', None),
        ('RSA_PUBLIC_KEY_FP', None),
        ('RSA_PUBLIC_KEY_2', None),
        ('RSA_PUBLIC_KEY_2_FP', None),
    ]


@pytest.fixture
def mock_snowflake_user_keys_null_string():
    """Mock user with 'null' string values (Snowflake quirk)."""
    return [
        ('RSA_PUBLIC_KEY', 'null'),
        ('RSA_PUBLIC_KEY_FP', 'null'),
        ('RSA_PUBLIC_KEY_2', None),
        ('RSA_PUBLIC_KEY_2_FP', None),
    ]


# =============================================================================
# Mock Fixtures for Hevo API
# =============================================================================

@pytest.fixture
def hevo_success_response():
    """Successful Hevo API response."""
    return {
        'success': True,
        'id': '12345',
        'destination_id': '12345',
        'name': 'test_destination'
    }


@pytest.fixture
def hevo_error_response():
    """Error Hevo API response."""
    return {
        'success': False,
        'error_message': 'Invalid authentication',
        'error_code': 401
    }
