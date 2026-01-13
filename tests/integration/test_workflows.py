"""
Integration tests for sf-rotation workflows.

These tests require real Snowflake and Hevo credentials.
Run with: pytest tests/integration/ -v --run-integration

WARNING: These tests will:
- Create/modify RSA keys in Snowflake
- Create/update destinations in Hevo
- Use the credentials in config/config.yaml

Only run against test/staging environments!
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path

from sf_rotation.main import run_setup, run_rotate, run_update_keys
from sf_rotation.utils import load_config
from sf_rotation.snowflake_client import SnowflakeClient
from sf_rotation.hevo_client import HevoClient


# Skip all tests in this module unless --run-integration is passed
pytestmark = pytest.mark.integration


@pytest.fixture
def integration_config():
    """
    Load real configuration for integration tests.
    
    Uses config/config.yaml from the project root.
    """
    config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
    
    if not config_path.exists():
        pytest.skip(f"Config file not found: {config_path}")
    
    config = load_config(str(config_path))
    
    # Validate required fields
    required_sf = ['account_url', 'username', 'password', 'user_to_modify']
    required_hevo = ['base_url', 'username', 'password']
    
    for field in required_sf:
        if not config.get('snowflake', {}).get(field):
            pytest.skip(f"Missing snowflake.{field} in config")
    
    for field in required_hevo:
        if not config.get('hevo', {}).get(field):
            pytest.skip(f"Missing hevo.{field} in config")
    
    return config


@pytest.fixture
def temp_keys_dir():
    """Create temporary directory for key files."""
    tmpdir = tempfile.mkdtemp(prefix='sf_rotation_test_')
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def snowflake_client(integration_config):
    """Create SnowflakeClient from integration config."""
    sf_config = integration_config['snowflake']
    return SnowflakeClient(
        account_url=sf_config['account_url'],
        username=sf_config['username'],
        password=sf_config['password'],
        warehouse=sf_config.get('warehouse'),
        database=sf_config.get('database')
    )


@pytest.fixture
def cleanup_snowflake_keys(snowflake_client, integration_config):
    """
    Fixture to clean up Snowflake keys after tests.
    
    Unsets both RSA key slots for the test user.
    """
    yield
    
    # Cleanup after test
    user = integration_config['snowflake']['user_to_modify']
    try:
        snowflake_client.unset_rsa_public_key(user)
    except Exception:
        pass
    try:
        snowflake_client.unset_rsa_public_key_2(user)
    except Exception:
        pass


class TestSnowflakeConnection:
    """Basic Snowflake connectivity tests."""
    
    def test_snowflake_connection(self, snowflake_client):
        """Test basic Snowflake connection."""
        result = snowflake_client.test_connection()
        assert result is True
    
    def test_get_user_public_keys(self, snowflake_client, integration_config):
        """Test retrieving user public key status."""
        user = integration_config['snowflake']['user_to_modify']
        key_info = snowflake_client.get_user_public_keys(user)
        
        assert 'RSA_PUBLIC_KEY' in key_info
        assert 'RSA_PUBLIC_KEY_2' in key_info
        assert 'RSA_PUBLIC_KEY_FP' in key_info
        assert 'RSA_PUBLIC_KEY_2_FP' in key_info


class TestHevoConnection:
    """Basic Hevo API connectivity tests."""
    
    def test_hevo_client_v1(self, integration_config):
        """Test Hevo client initialization with v1 API."""
        hevo_config = integration_config['hevo']
        client = HevoClient(
            base_url=hevo_config['base_url'],
            username=hevo_config['username'],
            password=hevo_config['password'],
            api_version='v1'
        )
        assert client.api_version == 'v1'
    
    def test_hevo_client_v2(self, integration_config):
        """Test Hevo client initialization with v2.0 API."""
        hevo_config = integration_config['hevo']
        client = HevoClient(
            base_url=hevo_config['base_url'],
            username=hevo_config['username'],
            password=hevo_config['password'],
            api_version='v2.0'
        )
        assert client.api_version == 'v2.0'


class TestKeyRotationWorkflow:
    """
    Full key rotation workflow tests.
    
    These tests perform actual key rotations against real services.
    """
    
    def test_rotate_keys_multiple_times(
        self, integration_config, temp_keys_dir, snowflake_client, cleanup_snowflake_keys
    ):
        """
        Test that key rotation works multiple times in succession.
        
        This is the core test for verifying the rotation mechanism:
        1. First rotation: slot 1 -> slot 2
        2. Second rotation: slot 2 -> slot 1
        3. Third rotation: slot 1 -> slot 2
        """
        config = integration_config.copy()
        config['keys']['output_directory'] = temp_keys_dir
        
        user = config['snowflake']['user_to_modify']
        
        # First, ensure we start with a clean slate
        try:
            snowflake_client.unset_rsa_public_key(user)
        except Exception:
            pass
        try:
            snowflake_client.unset_rsa_public_key_2(user)
        except Exception:
            pass
        
        # Skip Hevo interaction for this test - just test Snowflake rotation
        # This avoids the need for a real Hevo destination
        
        # We can't easily run the full workflow without Hevo,
        # but we can test the Snowflake key slot switching logic
        
        from sf_rotation.key_generator import KeyGenerator
        
        key_gen = KeyGenerator(output_directory=temp_keys_dir)
        
        # Generate and set first key in slot 1
        priv_path, pub_path, _ = key_gen.generate_key_pair('test_key', encrypted=False)
        pub_content = key_gen.read_public_key(pub_path)
        formatted_key = key_gen.format_public_key_for_snowflake(pub_content)
        
        snowflake_client.set_rsa_public_key(user, formatted_key)
        
        # Verify key is in slot 1
        keys = snowflake_client.get_user_public_keys(user)
        assert SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_FP'])
        assert not SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_2_FP'])
        
        # Simulate rotation 1: set new key in slot 2
        priv_path2, pub_path2, _ = key_gen.generate_key_pair('test_key2', encrypted=False)
        pub_content2 = key_gen.read_public_key(pub_path2)
        formatted_key2 = key_gen.format_public_key_for_snowflake(pub_content2)
        
        snowflake_client.set_rsa_public_key_2(user, formatted_key2)
        
        # Both keys should be set now
        keys = snowflake_client.get_user_public_keys(user)
        assert SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_FP'])
        assert SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_2_FP'])
        
        # Unset old key (slot 1)
        snowflake_client.unset_rsa_public_key(user)
        
        # Now only slot 2 should have key
        keys = snowflake_client.get_user_public_keys(user)
        assert not SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_FP'])
        assert SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_2_FP'])
        
        # Simulate rotation 2: set new key in slot 1
        priv_path3, pub_path3, _ = key_gen.generate_key_pair('test_key3', encrypted=False)
        pub_content3 = key_gen.read_public_key(pub_path3)
        formatted_key3 = key_gen.format_public_key_for_snowflake(pub_content3)
        
        snowflake_client.set_rsa_public_key(user, formatted_key3)
        snowflake_client.unset_rsa_public_key_2(user)
        
        # Now only slot 1 should have key
        keys = snowflake_client.get_user_public_keys(user)
        assert SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_FP'])
        assert not SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_2_FP'])
        
        # Verify we can continue rotating
        assert snowflake_client.get_available_key_slot(user) == 2


class TestFullWorkflowWithHevo:
    """
    Full workflow tests that include Hevo API calls.
    
    These tests require a valid Hevo destination to be configured.
    """
    
    @pytest.mark.skip(reason="Requires valid Hevo destination - run manually")
    def test_full_setup_workflow(
        self, integration_config, temp_keys_dir, cleanup_snowflake_keys
    ):
        """
        Test complete setup workflow.
        
        Creates new key pair, sets in Snowflake, creates Hevo destination.
        """
        config = integration_config.copy()
        config['keys']['output_directory'] = temp_keys_dir
        config['hevo']['destination_id'] = ''  # Clear for fresh setup
        
        # Determine API version based on base_url
        api_version = 'v2.0' if 'walrus' in config['hevo']['base_url'] else 'v1'
        
        result = run_setup(
            config,
            config_path='test.yaml',
            api_version=api_version
        )
        
        assert result is True
        
        # Verify keys were created
        assert os.path.exists(os.path.join(temp_keys_dir, 'rsa_key.p8'))
        assert os.path.exists(os.path.join(temp_keys_dir, 'rsa_key.pub'))
    
    @pytest.mark.skip(reason="Requires valid Hevo destination - run manually")  
    def test_full_rotate_workflow(
        self, integration_config, temp_keys_dir, cleanup_snowflake_keys
    ):
        """
        Test complete rotation workflow.
        
        Requires existing destination_id in config.
        """
        config = integration_config.copy()
        config['keys']['output_directory'] = temp_keys_dir
        
        if not config['hevo'].get('destination_id'):
            pytest.skip("No destination_id configured")
        
        api_version = 'v2.0' if 'walrus' in config['hevo']['base_url'] else 'v1'
        
        result = run_rotate(
            config,
            config_path='test.yaml',
            api_version=api_version
        )
        
        assert result is True


class TestEdgeCases:
    """Integration tests for edge cases."""
    
    def test_key_slot_detection_with_null_strings(
        self, snowflake_client, integration_config, cleanup_snowflake_keys
    ):
        """
        Test that null string handling works correctly.
        
        Snowflake sometimes returns 'null' as a string instead of None.
        """
        user = integration_config['snowflake']['user_to_modify']
        
        # Clear both keys
        try:
            snowflake_client.unset_rsa_public_key(user)
        except Exception:
            pass
        try:
            snowflake_client.unset_rsa_public_key_2(user)
        except Exception:
            pass
        
        # Get key info - fingerprints should be None or 'null'
        keys = snowflake_client.get_user_public_keys(user)
        
        # Both should be detected as not set
        assert not SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_FP'])
        assert not SnowflakeClient._is_key_set(keys['RSA_PUBLIC_KEY_2_FP'])
        
        # Available slot should be 1
        slot = snowflake_client.get_available_key_slot(user)
        assert slot == 1
