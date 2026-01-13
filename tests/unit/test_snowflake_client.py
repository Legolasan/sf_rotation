"""
Unit tests for SnowflakeClient.

Tests cover:
- RSA public key setting (slot 1 and 2)
- RSA public key unsetting
- Key slot availability detection
- Handling of Snowflake's various null representations
- Account extraction from URLs
"""

import pytest
from unittest.mock import patch, MagicMock

from sf_rotation.snowflake_client import SnowflakeClient, SnowflakeClientError


class TestSnowflakeClientInit:
    """Tests for SnowflakeClient initialization."""
    
    def test_extract_account_from_url(self):
        """Test account extraction from full URL."""
        client = SnowflakeClient(
            account_url='account.us-west-2.snowflakecomputing.com',
            username='user',
            password='pass'
        )
        assert client.account == 'account.us-west-2'
    
    def test_extract_account_with_https(self):
        """Test account extraction handles https:// prefix."""
        client = SnowflakeClient(
            account_url='https://account.snowflakecomputing.com',
            username='user',
            password='pass'
        )
        assert client.account == 'account'
    
    def test_extract_account_simple(self):
        """Test account extraction for simple account ID."""
        client = SnowflakeClient(
            account_url='NRMGHHK-QKB80056.snowflakecomputing.com',
            username='user',
            password='pass'
        )
        assert client.account == 'NRMGHHK-QKB80056'
    
    def test_optional_params_stored(self):
        """Test optional parameters are stored."""
        client = SnowflakeClient(
            account_url='account.snowflakecomputing.com',
            username='user',
            password='pass',
            warehouse='WH',
            database='DB',
            role='ROLE'
        )
        assert client.warehouse == 'WH'
        assert client.database == 'DB'
        assert client.role == 'ROLE'


class TestIsKeySet:
    """Tests for the _is_key_set static method."""
    
    def test_is_key_set_with_valid_fingerprint(self):
        """Test returns True for valid fingerprint."""
        assert SnowflakeClient._is_key_set('SHA256:abc123...') is True
    
    def test_is_key_set_with_none(self):
        """Test returns False for None."""
        assert SnowflakeClient._is_key_set(None) is False
    
    def test_is_key_set_with_empty_string(self):
        """Test returns False for empty string."""
        assert SnowflakeClient._is_key_set('') is False
    
    def test_is_key_set_with_null_string(self):
        """Test returns False for 'null' string (Snowflake quirk)."""
        assert SnowflakeClient._is_key_set('null') is False
    
    def test_is_key_set_with_null_uppercase(self):
        """Test returns False for 'NULL' string."""
        assert SnowflakeClient._is_key_set('NULL') is False
    
    def test_is_key_set_with_actual_key(self):
        """Test returns True for actual key content."""
        assert SnowflakeClient._is_key_set('MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...') is True


class TestSetRsaPublicKey:
    """Tests for setting RSA public keys."""
    
    @patch('snowflake.connector.connect')
    def test_set_rsa_public_key_slot1(self, mock_connect):
        """Test setting RSA_PUBLIC_KEY (slot 1)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        client.set_rsa_public_key('test_user', 'PUBLIC_KEY_CONTENT')
        
        # Verify the SQL executed
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert 'ALTER USER test_user SET RSA_PUBLIC_KEY=' in executed_sql
        assert 'PUBLIC_KEY_CONTENT' in executed_sql
    
    @patch('snowflake.connector.connect')
    def test_set_rsa_public_key_slot2(self, mock_connect):
        """Test setting RSA_PUBLIC_KEY_2 (slot 2)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        client.set_rsa_public_key_2('test_user', 'PUBLIC_KEY_CONTENT')
        
        # Verify the SQL executed
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert 'ALTER USER test_user SET RSA_PUBLIC_KEY_2=' in executed_sql
    
    @patch('snowflake.connector.connect')
    def test_set_key_strips_newlines(self, mock_connect):
        """Test key newlines are stripped."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        client.set_rsa_public_key('test_user', 'KEY\nWITH\nNEWLINES')
        
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert '\n' not in executed_sql
        assert 'KEYWITHNEWLINES' in executed_sql


class TestUnsetRsaPublicKey:
    """Tests for unsetting RSA public keys."""
    
    @patch('snowflake.connector.connect')
    def test_unset_rsa_public_key_slot1(self, mock_connect):
        """Test unsetting RSA_PUBLIC_KEY (slot 1)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        client.unset_rsa_public_key('test_user')
        
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert executed_sql == 'ALTER USER test_user UNSET RSA_PUBLIC_KEY'
    
    @patch('snowflake.connector.connect')
    def test_unset_rsa_public_key_slot2(self, mock_connect):
        """Test unsetting RSA_PUBLIC_KEY_2 (slot 2)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        client.unset_rsa_public_key_2('test_user')
        
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert executed_sql == 'ALTER USER test_user UNSET RSA_PUBLIC_KEY_2'


class TestGetAvailableKeySlot:
    """Tests for get_available_key_slot method."""
    
    @patch('snowflake.connector.connect')
    def test_get_available_key_slot_both_empty(self, mock_connect):
        """Test returns 1 when both slots are empty."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', None),
            ('RSA_PUBLIC_KEY_FP', None),
            ('RSA_PUBLIC_KEY_2', None),
            ('RSA_PUBLIC_KEY_2_FP', None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        slot = client.get_available_key_slot('test_user')
        
        assert slot == 1  # Prefer slot 1
    
    @patch('snowflake.connector.connect')
    def test_get_available_key_slot_1_occupied(self, mock_connect):
        """Test returns 2 when slot 1 is occupied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', 'KEY_CONTENT'),
            ('RSA_PUBLIC_KEY_FP', 'SHA256:abc123'),
            ('RSA_PUBLIC_KEY_2', None),
            ('RSA_PUBLIC_KEY_2_FP', None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        slot = client.get_available_key_slot('test_user')
        
        assert slot == 2
    
    @patch('snowflake.connector.connect')
    def test_get_available_key_slot_2_occupied(self, mock_connect):
        """Test returns 1 when only slot 2 is occupied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', None),
            ('RSA_PUBLIC_KEY_FP', None),
            ('RSA_PUBLIC_KEY_2', 'KEY_CONTENT'),
            ('RSA_PUBLIC_KEY_2_FP', 'SHA256:def456'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        slot = client.get_available_key_slot('test_user')
        
        assert slot == 1
    
    @patch('snowflake.connector.connect')
    def test_get_available_key_slot_both_occupied(self, mock_connect):
        """Test returns 0 when both slots are occupied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', 'KEY_CONTENT'),
            ('RSA_PUBLIC_KEY_FP', 'SHA256:abc123'),
            ('RSA_PUBLIC_KEY_2', 'KEY_CONTENT_2'),
            ('RSA_PUBLIC_KEY_2_FP', 'SHA256:def456'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        slot = client.get_available_key_slot('test_user')
        
        assert slot == 0
    
    @patch('snowflake.connector.connect')
    def test_get_available_key_slot_handles_null_string(self, mock_connect):
        """Test handles 'null' string as empty slot."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', 'null'),  # Snowflake quirk
            ('RSA_PUBLIC_KEY_FP', 'null'),
            ('RSA_PUBLIC_KEY_2', None),
            ('RSA_PUBLIC_KEY_2_FP', None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        slot = client.get_available_key_slot('test_user')
        
        assert slot == 1  # 'null' string should be treated as empty


class TestGetUserPublicKeys:
    """Tests for get_user_public_keys method."""
    
    @patch('snowflake.connector.connect')
    def test_get_user_public_keys_returns_dict(self, mock_connect):
        """Test returns dictionary with key info."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', 'KEY1'),
            ('RSA_PUBLIC_KEY_FP', 'FP1'),
            ('RSA_PUBLIC_KEY_2', 'KEY2'),
            ('RSA_PUBLIC_KEY_2_FP', 'FP2'),
            ('OTHER_PROP', 'VALUE'),  # Should be ignored
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        result = client.get_user_public_keys('test_user')
        
        assert result['RSA_PUBLIC_KEY'] == 'KEY1'
        assert result['RSA_PUBLIC_KEY_FP'] == 'FP1'
        assert result['RSA_PUBLIC_KEY_2'] == 'KEY2'
        assert result['RSA_PUBLIC_KEY_2_FP'] == 'FP2'
        assert 'OTHER_PROP' not in result


class TestVerifyKeySetup:
    """Tests for verify_key_setup method."""
    
    @patch('snowflake.connector.connect')
    def test_verify_key_setup_with_key1(self, mock_connect):
        """Test returns True when key 1 is set."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', 'KEY'),
            ('RSA_PUBLIC_KEY_FP', 'SHA256:abc'),
            ('RSA_PUBLIC_KEY_2', None),
            ('RSA_PUBLIC_KEY_2_FP', None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        result = client.verify_key_setup('test_user')
        
        assert result is True
    
    @patch('snowflake.connector.connect')
    def test_verify_key_setup_with_key2(self, mock_connect):
        """Test returns True when key 2 is set."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', None),
            ('RSA_PUBLIC_KEY_FP', None),
            ('RSA_PUBLIC_KEY_2', 'KEY'),
            ('RSA_PUBLIC_KEY_2_FP', 'SHA256:def'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        result = client.verify_key_setup('test_user')
        
        assert result is True
    
    @patch('snowflake.connector.connect')
    def test_verify_key_setup_no_keys(self, mock_connect):
        """Test returns False when no keys are set."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('RSA_PUBLIC_KEY', None),
            ('RSA_PUBLIC_KEY_FP', None),
            ('RSA_PUBLIC_KEY_2', None),
            ('RSA_PUBLIC_KEY_2_FP', None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        result = client.verify_key_setup('test_user')
        
        assert result is False


class TestConnectionErrors:
    """Tests for connection error handling."""
    
    @patch('snowflake.connector.connect')
    def test_connection_error_raises_client_error(self, mock_connect):
        """Test connection failure raises SnowflakeClientError."""
        import snowflake.connector.errors
        mock_connect.side_effect = snowflake.connector.errors.DatabaseError("Connection failed")
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        
        with pytest.raises(SnowflakeClientError, match="Connection failed"):
            client.test_connection()
    
    @patch('snowflake.connector.connect')
    def test_set_key_error_raises_client_error(self, mock_connect):
        """Test set key failure raises SnowflakeClientError."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Permission denied")
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        client = SnowflakeClient('account.snowflakecomputing.com', 'user', 'pass')
        
        with pytest.raises(SnowflakeClientError, match="Permission denied"):
            client.set_rsa_public_key('test_user', 'KEY')
