"""
Unit tests for HevoClient.

Tests cover:
- v1 and v2.0 API payload generation
- Account name extraction from URLs
- Region extraction from URLs
- HTTP method selection (PATCH vs PUT)
- Error handling
"""

import pytest
import responses
from unittest.mock import patch, MagicMock

from sf_rotation.hevo_client import HevoClient, HevoClientError


class TestHevoClientInit:
    """Tests for HevoClient initialization."""
    
    def test_init_v1_default(self):
        """Test default initialization uses v1 API."""
        client = HevoClient(
            base_url='https://us.hevodata.com',
            username='user',
            password='pass'
        )
        assert client.api_version == 'v1'
        assert client.base_url == 'https://us.hevodata.com'
    
    def test_init_v2(self):
        """Test v2.0 API initialization."""
        client = HevoClient(
            base_url='https://s-walrus.hevo.me',
            username='user',
            password='pass',
            api_version='v2.0'
        )
        assert client.api_version == 'v2.0'
    
    def test_init_invalid_version_raises(self):
        """Test invalid API version raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported API version"):
            HevoClient(
                base_url='https://us.hevodata.com',
                username='user',
                password='pass',
                api_version='v3.0'
            )
    
    def test_init_strips_trailing_slash(self):
        """Test base_url trailing slash is stripped."""
        client = HevoClient(
            base_url='https://us.hevodata.com/',
            username='user',
            password='pass'
        )
        assert client.base_url == 'https://us.hevodata.com'


class TestGetUrl:
    """Tests for URL generation."""
    
    def test_get_url_v1(self):
        """Test v1 API URL generation."""
        client = HevoClient(
            base_url='https://us.hevodata.com',
            username='user',
            password='pass',
            api_version='v1'
        )
        url = client._get_url('destinations')
        assert url == 'https://us.hevodata.com/api/v1/destinations'
    
    def test_get_url_v2(self):
        """Test v2.0 API URL generation."""
        client = HevoClient(
            base_url='https://s-walrus.hevo.me',
            username='user',
            password='pass',
            api_version='v2.0'
        )
        url = client._get_url('destinations')
        assert url == 'https://s-walrus.hevo.me/api/public/v2.0/destinations'
    
    def test_get_url_with_id(self):
        """Test URL generation with destination ID."""
        client = HevoClient(
            base_url='https://us.hevodata.com',
            username='user',
            password='pass',
            api_version='v1'
        )
        url = client._get_url('destinations/12345')
        assert url == 'https://us.hevodata.com/api/v1/destinations/12345'


class TestExtractAccountName:
    """Tests for account name extraction from Snowflake URLs."""
    
    def test_extract_account_name_with_region(self):
        """Test extraction from URL with region: xxx.us-west-2.snowflakecomputing.com -> xxx"""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_account_name('xxx.us-west-2.snowflakecomputing.com')
        assert result == 'xxx'
    
    def test_extract_account_name_without_region(self):
        """Test extraction from URL without region: ACCOUNT.snowflakecomputing.com -> ACCOUNT"""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_account_name('NRMGHHK-QKB80056.snowflakecomputing.com')
        assert result == 'NRMGHHK-QKB80056'
    
    def test_extract_account_name_with_https(self):
        """Test extraction handles https:// prefix."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_account_name('https://xxx.us-west-2.snowflakecomputing.com')
        assert result == 'xxx'
    
    def test_extract_account_name_with_http(self):
        """Test extraction handles http:// prefix."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_account_name('http://account.snowflakecomputing.com')
        assert result == 'account'


class TestExtractRegion:
    """Tests for region extraction from Snowflake URLs."""
    
    def test_extract_region_from_url(self):
        """Test region extraction from URL with region."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_region('xxx.us-west-2.snowflakecomputing.com')
        assert result == 'us-west-2'
    
    def test_extract_region_eu_west(self):
        """Test region extraction for EU region."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_region('account.eu-west-1.snowflakecomputing.com')
        assert result == 'eu-west-1'
    
    def test_extract_region_fallback(self):
        """Test region fallback when not in URL."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        # URL without region (only one part before .snowflakecomputing.com)
        result = client._extract_region('NRMGHHK-QKB80056.snowflakecomputing.com')
        assert result == 'us-west-2'  # Default fallback
    
    def test_extract_region_with_https(self):
        """Test region extraction handles https:// prefix."""
        client = HevoClient('https://test.com', 'user', 'pass')
        
        result = client._extract_region('https://xxx.ap-southeast-1.snowflakecomputing.com')
        assert result == 'ap-southeast-1'


class TestBuildCreatePayload:
    """Tests for create destination payload generation."""
    
    def test_build_create_payload_v1(self):
        """Test v1 API create payload structure."""
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        
        payload = client._build_create_payload(
            name='test_dest',
            account_url='account.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----'
        )
        
        assert payload['destination_type'] == 'SNOWFLAKE'
        assert payload['name'] == 'test_dest'
        assert payload['connector_id'] == 'snowflake'
        assert payload['config']['authentication_type'] == 'PRIVATE_KEY'
        assert payload['config']['account_url'] == 'account.snowflakecomputing.com'
        assert payload['config']['warehouse'] == 'WH'
        assert payload['config']['database_name'] == 'DB'
        assert payload['config']['database_user'] == 'USER'
    
    def test_build_create_payload_v2(self):
        """Test v2.0 API create payload structure."""
        client = HevoClient('https://s-walrus.hevo.me', 'user', 'pass', api_version='v2.0')
        
        payload = client._build_create_payload(
            name='test_dest',
            account_url='xxx.us-west-2.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='KEY',
            region='us-west-2'
        )
        
        assert payload['type'] == 'SNOWFLAKE'
        assert payload['name'] == 'test_dest'
        assert payload['config']['authentication_type'] == 'KEY_PAIR'
        assert payload['config']['account_name'] == 'xxx'  # Extracted, not full URL
        assert payload['config']['region'] == 'us-west-2'
        assert payload['config']['warehouse'] == 'WH'
        assert payload['config']['db_name'] == 'DB'
        assert payload['config']['db_user'] == 'USER'
    
    def test_build_create_payload_v2_extracts_region(self):
        """Test v2.0 API extracts region from URL if not provided."""
        client = HevoClient('https://s-walrus.hevo.me', 'user', 'pass', api_version='v2.0')
        
        payload = client._build_create_payload(
            name='test_dest',
            account_url='xxx.eu-central-1.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='KEY'
            # region not provided - should be extracted
        )
        
        assert payload['config']['region'] == 'eu-central-1'
    
    def test_build_create_payload_with_passphrase(self):
        """Test payload includes passphrase when provided."""
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        
        payload = client._build_create_payload(
            name='test_dest',
            account_url='account.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='KEY',
            private_key_passphrase='secret123'
        )
        
        assert payload['config']['private_key_passphrase'] == 'secret123'
    
    def test_build_create_payload_strips_whitespace(self):
        """Test private key whitespace is stripped."""
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        
        payload = client._build_create_payload(
            name='test_dest',
            account_url='account.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='  KEY_WITH_SPACES  \n'
        )
        
        assert payload['config']['private_key'] == 'KEY_WITH_SPACES'


class TestBuildUpdatePayload:
    """Tests for update destination payload generation."""
    
    def test_build_update_payload_v1_minimal(self):
        """Test v1 API update payload is minimal (key only)."""
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        
        payload = client._build_update_payload(
            private_key='NEW_KEY',
            connector_id='snowflake'
        )
        
        assert payload['config']['authentication_type'] == 'PRIVATE_KEY'
        assert payload['config']['private_key'] == 'NEW_KEY'
        assert payload['connector_id'] == 'snowflake'
        # Should NOT have account_url, warehouse, etc.
        assert 'account_url' not in payload['config']
    
    def test_build_update_payload_v2_full_config(self):
        """Test v2.0 API update payload includes full config."""
        client = HevoClient('https://s-walrus.hevo.me', 'user', 'pass', api_version='v2.0')
        
        payload = client._build_update_payload(
            private_key='NEW_KEY',
            account_url='xxx.us-west-2.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            region='us-west-2'
        )
        
        assert payload['config']['authentication_type'] == 'KEY_PAIR'
        assert payload['config']['private_key'] == 'NEW_KEY'
        assert payload['config']['account_name'] == 'xxx'
        assert payload['config']['region'] == 'us-west-2'
        assert payload['config']['warehouse'] == 'WH'
        assert payload['config']['db_name'] == 'DB'
        assert payload['config']['db_user'] == 'USER'


class TestCreateDestination:
    """Tests for create_destination API call."""
    
    @responses.activate
    def test_create_destination_v1_uses_post(self):
        """Test v1 create uses POST method."""
        responses.add(
            responses.POST,
            'https://us.hevodata.com/api/v1/destinations',
            json={'success': True, 'id': '123'},
            status=200
        )
        
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        result = client.create_destination(
            name='test',
            account_url='account.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='KEY'
        )
        
        assert result['id'] == '123'
        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == 'POST'
    
    @responses.activate
    def test_create_destination_v2_uses_post(self):
        """Test v2.0 create uses POST method."""
        responses.add(
            responses.POST,
            'https://s-walrus.hevo.me/api/public/v2.0/destinations',
            json={'success': True, 'id': '1'},
            status=200
        )
        
        client = HevoClient('https://s-walrus.hevo.me', 'user', 'pass', api_version='v2.0')
        result = client.create_destination(
            name='test',
            account_url='xxx.us-west-2.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            private_key='KEY',
            region='us-west-2'
        )
        
        assert result['id'] == '1'


class TestUpdateDestination:
    """Tests for update_destination API call."""
    
    @responses.activate
    def test_update_destination_v1_uses_patch(self):
        """Test v1 update uses PATCH method."""
        responses.add(
            responses.PATCH,
            'https://us.hevodata.com/api/v1/destinations/123',
            json={'success': True},
            status=200
        )
        
        client = HevoClient('https://us.hevodata.com', 'user', 'pass', api_version='v1')
        client.update_destination(
            destination_id='123',
            private_key='NEW_KEY'
        )
        
        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == 'PATCH'
    
    @responses.activate
    def test_update_destination_v2_uses_put(self):
        """Test v2.0 update uses PUT method."""
        responses.add(
            responses.PUT,
            'https://s-walrus.hevo.me/api/public/v2.0/destinations/1',
            json={'success': True},
            status=200
        )
        
        client = HevoClient('https://s-walrus.hevo.me', 'user', 'pass', api_version='v2.0')
        client.update_destination(
            destination_id='1',
            private_key='NEW_KEY',
            account_url='xxx.us-west-2.snowflakecomputing.com',
            warehouse='WH',
            database_name='DB',
            database_user='USER',
            region='us-west-2'
        )
        
        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == 'PUT'


class TestErrorHandling:
    """Tests for API error handling."""
    
    @responses.activate
    def test_http_400_raises_error(self):
        """Test 400 Bad Request raises HevoClientError."""
        responses.add(
            responses.POST,
            'https://us.hevodata.com/api/v1/destinations',
            json={'error': 'Bad request'},
            status=400
        )
        
        client = HevoClient('https://us.hevodata.com', 'user', 'pass')
        
        with pytest.raises(HevoClientError, match="API request failed"):
            client.create_destination(
                name='test',
                account_url='account.snowflakecomputing.com',
                warehouse='WH',
                database_name='DB',
                database_user='USER',
                private_key='KEY'
            )
    
    @responses.activate
    def test_http_401_raises_error(self):
        """Test 401 Unauthorized raises HevoClientError."""
        responses.add(
            responses.POST,
            'https://us.hevodata.com/api/v1/destinations',
            json={'error': 'Unauthorized'},
            status=401
        )
        
        client = HevoClient('https://us.hevodata.com', 'user', 'pass')
        
        with pytest.raises(HevoClientError, match="API request failed.*401"):
            client.create_destination(
                name='test',
                account_url='account.snowflakecomputing.com',
                warehouse='WH',
                database_name='DB',
                database_user='USER',
                private_key='KEY'
            )
    
    @responses.activate
    def test_http_500_raises_error(self):
        """Test 500 Internal Server Error raises HevoClientError."""
        responses.add(
            responses.POST,
            'https://us.hevodata.com/api/v1/destinations',
            json={'success': False, 'error_message': 'Internal error'},
            status=500
        )
        
        client = HevoClient('https://us.hevodata.com', 'user', 'pass')
        
        with pytest.raises(HevoClientError, match="API request failed.*500"):
            client.create_destination(
                name='test',
                account_url='account.snowflakecomputing.com',
                warehouse='WH',
                database_name='DB',
                database_user='USER',
                private_key='KEY'
            )
