"""
Unit tests for main.py workflow functions.

Tests cover:
- setup workflow edge cases
- update-keys workflow edge cases
- rotate workflow edge cases (slot switching, multiple rotations)
- Error handling and validation
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from sf_rotation.main import run_setup, run_rotate, run_update_keys


class TestRunSetupEdgeCases:
    """Tests for run_setup workflow edge cases."""
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.save_config')
    @patch('sf_rotation.main.confirm_action', return_value=True)
    def test_setup_with_existing_destination_id_prompts(
        self, mock_confirm, mock_save, mock_keygen, mock_sf_client, mock_hevo_client,
        sample_config
    ):
        """Test setup with existing destination_id warns user."""
        # Config already has destination_id
        config = sample_config.copy()
        config['hevo']['destination_id'] = '12345'
        
        # User declines to create new
        mock_confirm.return_value = False
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            result = run_setup(config, config_path='test.yaml')
        
        # Should have asked for confirmation
        assert mock_confirm.called
        # Should return False when user declines
        assert result is False
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.save_config')
    @patch('sf_rotation.main.confirm_action', return_value=True)
    def test_setup_fails_when_both_slots_occupied(
        self, mock_confirm, mock_save, mock_keygen_class, mock_sf_client_class, mock_hevo_client,
        sample_config_no_destination_id
    ):
        """Test setup fails gracefully when both key slots are occupied."""
        config = sample_config_no_destination_id.copy()
        
        # Mock SnowflakeClient
        mock_sf = MagicMock()
        mock_sf.get_available_key_slot.return_value = 0  # Both occupied
        mock_sf_client_class.return_value = mock_sf
        
        # Mock KeyGenerator
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
        mock_keygen.read_private_key.return_value = 'PRIVATE_KEY'
        mock_keygen.read_public_key.return_value = 'PUBLIC_KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'FORMATTED_KEY'
        mock_keygen_class.return_value = mock_keygen
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            result = run_setup(config, config_path='test.yaml')
        
        # Should fail
        assert result is False
        # Hevo should not be called
        mock_hevo_client.assert_not_called()


class TestRunRotateEdgeCases:
    """Tests for run_rotate workflow edge cases."""
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.backup_keys')
    @patch('sf_rotation.main.confirm_action', return_value=True)
    def test_rotate_slot1_to_slot2(
        self, mock_confirm, mock_backup, mock_keygen_class, mock_sf_client_class, mock_hevo_client_class,
        sample_config
    ):
        """Test rotation from slot 1 to slot 2."""
        config = sample_config.copy()
        
        # Mock SnowflakeClient - key in slot 1
        mock_sf = MagicMock()
        mock_sf.get_user_public_keys.return_value = {
            'RSA_PUBLIC_KEY': 'KEY',
            'RSA_PUBLIC_KEY_FP': 'SHA256:abc',
            'RSA_PUBLIC_KEY_2': None,
            'RSA_PUBLIC_KEY_2_FP': None,
        }
        mock_sf._is_key_set = lambda fp: fp is not None and fp != '' and str(fp).lower() != 'null'
        mock_sf_client_class.return_value = mock_sf
        
        # Mock KeyGenerator
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/new_key.p8', '/tmp/new_key.pub', None)
        mock_keygen.read_private_key.return_value = 'NEW_PRIVATE_KEY'
        mock_keygen.read_public_key.return_value = 'NEW_PUBLIC_KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'FORMATTED_KEY'
        mock_keygen_class.return_value = mock_keygen
        
        # Mock HevoClient
        mock_hevo = MagicMock()
        mock_hevo_client_class.return_value = mock_hevo
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            # Create dummy key files
            Path(tmpdir, 'rsa_key.p8').touch()
            Path(tmpdir, 'rsa_key.pub').touch()
            
            result = run_rotate(config, config_path='test.yaml')
        
        # Should set key in slot 2
        mock_sf.set_rsa_public_key_2.assert_called_once()
        # Should unset slot 1 after confirmation
        mock_sf.unset_rsa_public_key.assert_called_once()
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.backup_keys')
    @patch('sf_rotation.main.confirm_action', return_value=True)
    def test_rotate_slot2_to_slot1(
        self, mock_confirm, mock_backup, mock_keygen_class, mock_sf_client_class, mock_hevo_client_class,
        sample_config
    ):
        """Test rotation from slot 2 to slot 1."""
        config = sample_config.copy()
        
        # Mock SnowflakeClient - key in slot 2
        mock_sf = MagicMock()
        mock_sf.get_user_public_keys.return_value = {
            'RSA_PUBLIC_KEY': None,
            'RSA_PUBLIC_KEY_FP': None,
            'RSA_PUBLIC_KEY_2': 'KEY',
            'RSA_PUBLIC_KEY_2_FP': 'SHA256:def',
        }
        mock_sf._is_key_set = lambda fp: fp is not None and fp != '' and str(fp).lower() != 'null'
        mock_sf_client_class.return_value = mock_sf
        
        # Mock KeyGenerator
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/new_key.p8', '/tmp/new_key.pub', None)
        mock_keygen.read_private_key.return_value = 'NEW_PRIVATE_KEY'
        mock_keygen.read_public_key.return_value = 'NEW_PUBLIC_KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'FORMATTED_KEY'
        mock_keygen_class.return_value = mock_keygen
        
        # Mock HevoClient
        mock_hevo = MagicMock()
        mock_hevo_client_class.return_value = mock_hevo
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            Path(tmpdir, 'rsa_key.p8').touch()
            Path(tmpdir, 'rsa_key.pub').touch()
            
            result = run_rotate(config, config_path='test.yaml')
        
        # Should set key in slot 1
        mock_sf.set_rsa_public_key.assert_called_once()
        # Should unset slot 2 after confirmation
        mock_sf.unset_rsa_public_key_2.assert_called_once()
    
    def test_rotate_fails_when_both_slots_occupied(self, sample_config):
        """Test rotate fails when both slots are occupied."""
        config = sample_config.copy()
        
        with patch('sf_rotation.main.SnowflakeClient') as mock_sf_client_class:
            with patch('sf_rotation.main.KeyGenerator') as mock_keygen_class:
                with patch('sf_rotation.main.backup_keys'):
                    # Mock SnowflakeClient - both slots occupied
                    mock_sf = MagicMock()
                    mock_sf.get_user_public_keys.return_value = {
                        'RSA_PUBLIC_KEY': 'KEY1',
                        'RSA_PUBLIC_KEY_FP': 'SHA256:abc',
                        'RSA_PUBLIC_KEY_2': 'KEY2',
                        'RSA_PUBLIC_KEY_2_FP': 'SHA256:def',
                    }
                    mock_sf._is_key_set = lambda fp: fp is not None and fp != '' and str(fp).lower() != 'null'
                    mock_sf_client_class.return_value = mock_sf
                    
                    # Mock KeyGenerator
                    mock_keygen = MagicMock()
                    mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
                    mock_keygen.read_private_key.return_value = 'KEY'
                    mock_keygen.read_public_key.return_value = 'KEY'
                    mock_keygen.format_public_key_for_snowflake.return_value = 'KEY'
                    mock_keygen_class.return_value = mock_keygen
                    
                    with tempfile.TemporaryDirectory() as tmpdir:
                        config['keys']['output_directory'] = tmpdir
                        result = run_rotate(config, config_path='test.yaml')
                    
                    # Should fail
                    assert result is False
    
    def test_rotate_fails_when_no_keys_set(self, sample_config):
        """Test rotate fails when no keys are currently set."""
        config = sample_config.copy()
        
        with patch('sf_rotation.main.SnowflakeClient') as mock_sf_client_class:
            with patch('sf_rotation.main.KeyGenerator') as mock_keygen_class:
                with patch('sf_rotation.main.backup_keys'):
                    # Mock SnowflakeClient - no keys set
                    mock_sf = MagicMock()
                    mock_sf.get_user_public_keys.return_value = {
                        'RSA_PUBLIC_KEY': None,
                        'RSA_PUBLIC_KEY_FP': None,
                        'RSA_PUBLIC_KEY_2': None,
                        'RSA_PUBLIC_KEY_2_FP': None,
                    }
                    mock_sf._is_key_set = lambda fp: fp is not None and fp != '' and str(fp).lower() != 'null'
                    mock_sf_client_class.return_value = mock_sf
                    
                    # Mock KeyGenerator
                    mock_keygen = MagicMock()
                    mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
                    mock_keygen.read_private_key.return_value = 'KEY'
                    mock_keygen.read_public_key.return_value = 'KEY'
                    mock_keygen.format_public_key_for_snowflake.return_value = 'KEY'
                    mock_keygen_class.return_value = mock_keygen
                    
                    with tempfile.TemporaryDirectory() as tmpdir:
                        config['keys']['output_directory'] = tmpdir
                        result = run_rotate(config, config_path='test.yaml')
                    
                    # Should fail - should use setup first
                    assert result is False
    
    def test_rotate_fails_without_destination_id(self, sample_config_no_destination_id):
        """Test rotate fails when destination_id is not configured."""
        config = sample_config_no_destination_id.copy()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            result = run_rotate(config, config_path='test.yaml')
        
        # Should fail immediately
        assert result is False


class TestRunUpdateKeysEdgeCases:
    """Tests for run_update_keys workflow edge cases."""
    
    def test_update_keys_fails_without_destination_id(self, sample_config_no_destination_id):
        """Test update-keys fails when destination_id is not configured."""
        config = sample_config_no_destination_id.copy()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            result = run_update_keys(config, config_path='test.yaml')
        
        # Should fail immediately
        assert result is False
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    def test_update_keys_fails_when_both_slots_occupied(
        self, mock_keygen_class, mock_sf_client_class, mock_hevo_client,
        sample_config
    ):
        """Test update-keys fails when both key slots are occupied."""
        config = sample_config.copy()
        
        # Mock SnowflakeClient
        mock_sf = MagicMock()
        mock_sf.get_available_key_slot.return_value = 0  # Both occupied
        mock_sf_client_class.return_value = mock_sf
        
        # Mock KeyGenerator
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
        mock_keygen.read_private_key.return_value = 'PRIVATE_KEY'
        mock_keygen.read_public_key.return_value = 'PUBLIC_KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'FORMATTED_KEY'
        mock_keygen_class.return_value = mock_keygen
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            result = run_update_keys(config, config_path='test.yaml')
        
        # Should fail
        assert result is False


class TestMultipleRotations:
    """Tests for multiple consecutive rotations."""
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.backup_keys')
    @patch('sf_rotation.main.confirm_action', return_value=True)
    def test_rotate_alternates_slots(
        self, mock_confirm, mock_backup, mock_keygen_class, mock_sf_client_class, mock_hevo_client_class,
        sample_config
    ):
        """Test multiple rotations alternate between slots correctly."""
        config = sample_config.copy()
        
        # First rotation: key in slot 1 -> new key in slot 2 -> unset slot 1
        mock_sf = MagicMock()
        mock_sf.get_user_public_keys.return_value = {
            'RSA_PUBLIC_KEY': 'KEY',
            'RSA_PUBLIC_KEY_FP': 'SHA256:abc',
            'RSA_PUBLIC_KEY_2': None,
            'RSA_PUBLIC_KEY_2_FP': None,
        }
        mock_sf._is_key_set = lambda fp: fp is not None and fp != '' and str(fp).lower() != 'null'
        mock_sf_client_class.return_value = mock_sf
        
        # Mock KeyGenerator
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
        mock_keygen.read_private_key.return_value = 'KEY'
        mock_keygen.read_public_key.return_value = 'KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'KEY'
        mock_keygen_class.return_value = mock_keygen
        
        # Mock HevoClient
        mock_hevo = MagicMock()
        mock_hevo_client_class.return_value = mock_hevo
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            Path(tmpdir, 'rsa_key.p8').touch()
            Path(tmpdir, 'rsa_key.pub').touch()
            
            run_rotate(config, config_path='test.yaml')
        
        # Verify slot 2 was set (new key) - key was in slot 1, so new goes to slot 2
        mock_sf.set_rsa_public_key_2.assert_called_once()
        # Verify slot 1 was unset (old key)
        mock_sf.unset_rsa_public_key.assert_called_once()


class TestApiVersionPassing:
    """Tests for API version parameter passing."""
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.save_config')
    @patch('sf_rotation.main.confirm_action', return_value=False)
    def test_setup_passes_api_version_v1(
        self, mock_confirm, mock_save, mock_keygen_class, mock_sf_client_class, mock_hevo_client_class,
        sample_config_no_destination_id
    ):
        """Test setup passes v1 API version to HevoClient."""
        config = sample_config_no_destination_id.copy()
        
        # Setup mocks minimally to reach HevoClient instantiation
        mock_sf = MagicMock()
        mock_sf.get_available_key_slot.return_value = 1
        mock_sf_client_class.return_value = mock_sf
        
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
        mock_keygen.read_private_key.return_value = 'KEY'
        mock_keygen.read_public_key.return_value = 'KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'KEY'
        mock_keygen_class.return_value = mock_keygen
        
        mock_hevo = MagicMock()
        mock_hevo.create_destination.return_value = {'id': '123'}
        mock_hevo_client_class.return_value = mock_hevo
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            run_setup(config, config_path='test.yaml', api_version='v1')
        
        # Verify HevoClient was instantiated with v1
        mock_hevo_client_class.assert_called_once()
        call_kwargs = mock_hevo_client_class.call_args[1]
        assert call_kwargs['api_version'] == 'v1'
    
    @patch('sf_rotation.main.HevoClient')
    @patch('sf_rotation.main.SnowflakeClient')
    @patch('sf_rotation.main.KeyGenerator')
    @patch('sf_rotation.main.save_config')
    @patch('sf_rotation.main.confirm_action', return_value=False)
    def test_setup_passes_api_version_v2(
        self, mock_confirm, mock_save, mock_keygen_class, mock_sf_client_class, mock_hevo_client_class,
        sample_config_no_destination_id
    ):
        """Test setup passes v2.0 API version to HevoClient."""
        config = sample_config_no_destination_id.copy()
        
        mock_sf = MagicMock()
        mock_sf.get_available_key_slot.return_value = 1
        mock_sf_client_class.return_value = mock_sf
        
        mock_keygen = MagicMock()
        mock_keygen.generate_key_pair.return_value = ('/tmp/key.p8', '/tmp/key.pub', None)
        mock_keygen.read_private_key.return_value = 'KEY'
        mock_keygen.read_public_key.return_value = 'KEY'
        mock_keygen.format_public_key_for_snowflake.return_value = 'KEY'
        mock_keygen_class.return_value = mock_keygen
        
        mock_hevo = MagicMock()
        mock_hevo.create_destination.return_value = {'id': '1'}
        mock_hevo_client_class.return_value = mock_hevo
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config['keys']['output_directory'] = tmpdir
            run_setup(config, config_path='test.yaml', api_version='v2.0')
        
        # Verify HevoClient was instantiated with v2.0
        mock_hevo_client_class.assert_called_once()
        call_kwargs = mock_hevo_client_class.call_args[1]
        assert call_kwargs['api_version'] == 'v2.0'
