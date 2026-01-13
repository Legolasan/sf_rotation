"""
Hevo Data API Client Module

Manages Hevo Data destination configurations via REST API.
Supports creating and updating Snowflake destinations with key-pair authentication.
"""

import requests
from typing import Optional, Dict, Any
from requests.auth import HTTPBasicAuth


class HevoClientError(Exception):
    """Custom exception for Hevo API client errors."""
    pass


class HevoClient:
    """
    Client for interacting with Hevo Data REST API.
    
    Provides methods to create and update Snowflake destinations
    with key-pair authentication support.
    
    Supports two API versions:
    - v1 (Production): /api/v1/destinations
    - v2.0 (Testing): /api/public/v2.0/destinations
    """
    
    # Supported API versions
    SUPPORTED_VERSIONS = ["v1", "v2.0"]
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        api_version: str = "v1"
    ):
        """
        Initialize the Hevo API client.
        
        Args:
            base_url: Hevo API base URL (e.g., 'https://us.hevodata.com')
            username: Hevo account username for Basic Auth
            password: Hevo account password for Basic Auth
            api_version: API version to use ('v1' for production, 'v2.0' for testing)
        """
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if api_version not in self.SUPPORTED_VERSIONS:
            raise ValueError(f"Unsupported API version: {api_version}. Supported: {self.SUPPORTED_VERSIONS}")
        self.api_version = api_version
    
    def _get_url(self, endpoint: str) -> str:
        """
        Build full API URL for an endpoint.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Full URL string
        """
        if self.api_version == "v2.0":
            return f"{self.base_url}/api/public/v2.0/{endpoint.lstrip('/')}"
        return f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and raise appropriate errors.
        
        Args:
            response: Response object from requests
            
        Returns:
            JSON response as dictionary
            
        Raises:
            HevoClientError: If the API returns an error
        """
        try:
            data = response.json()
        except ValueError:
            data = {'raw_response': response.text}
        
        if response.status_code >= 400:
            error_msg = data.get('message', data.get('error', str(data)))
            raise HevoClientError(
                f"API request failed (HTTP {response.status_code}): {error_msg}"
            )
        
        return data
    
    def _extract_account_name(self, account_url: str) -> str:
        """
        Extract account name from Snowflake account URL.
        
        Handles both formats:
            - 'account.snowflakecomputing.com' -> 'account'
            - 'account.region.snowflakecomputing.com' -> 'account'
        
        Args:
            account_url: Full account URL
            
        Returns:
            Account name/identifier (without region)
        """
        # Remove protocol if present
        account = account_url.replace('https://', '').replace('http://', '')
        # Remove .snowflakecomputing.com suffix if present
        account = account.replace('.snowflakecomputing.com', '')
        # Return only the first part (account identifier, not region)
        parts = account.split('.')
        return parts[0]
    
    def _extract_region(self, account_url: str) -> str:
        """
        Extract AWS region from Snowflake account URL.
        
        Args:
            account_url: Full account URL (e.g., 'xxx.us-west-2.snowflakecomputing.com')
            
        Returns:
            AWS region (e.g., 'us-west-2'). Defaults to 'us-west-2' if not found.
        """
        # Remove protocol if present
        account = account_url.replace('https://', '').replace('http://', '')
        # Remove .snowflakecomputing.com suffix if present
        account = account.replace('.snowflakecomputing.com', '')
        
        # Split by '.' and find region (e.g., xxx.us-west-2 -> us-west-2)
        parts = account.split('.')
        if len(parts) >= 2:
            return parts[1]
        return 'us-west-2'
    
    def _build_create_payload(
        self,
        name: str,
        account_url: str,
        warehouse: str,
        database_name: str,
        database_user: str,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake",
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build the create destination payload based on API version.
        
        v1 (Production) schema:
            - destination_type, account_url, database_name, database_user, PRIVATE_KEY
            
        v2.0 (Testing) schema:
            - type, account_name, db_name, db_user, KEY_PAIR, region_id
        """
        # Strip leading/trailing whitespace from private key
        clean_private_key = private_key.strip() if private_key else private_key
        
        if self.api_version == "v2.0":
            # v2.0 API schema (Testing)
            # Use explicit region if provided, otherwise try to extract from URL
            region_value = region if region else self._extract_region(account_url)
            config = {
                "authentication_type": "KEY_PAIR",
                "account_name": self._extract_account_name(account_url),
                "region": region_value,
                "warehouse": warehouse,
                "db_name": database_name,
                "db_user": database_user,
                "private_key": clean_private_key
            }
            
            if private_key_passphrase:
                config["private_key_passphrase"] = private_key_passphrase
            
            payload = {
                "type": "SNOWFLAKE",
                "config": config,
                "name": name
            }
        else:
            # v1 API schema (Production)
            config = {
                "authentication_type": "PRIVATE_KEY",
                "account_url": account_url,
                "warehouse": warehouse,
                "database_name": database_name,
                "database_user": database_user,
                "private_key": clean_private_key
            }
            
            if private_key_passphrase:
                config["private_key_passphrase"] = private_key_passphrase
            
            payload = {
                "destination_type": "SNOWFLAKE",
                "config": config,
                "connector_id": connector_id,
                "name": name
            }
        
        return payload
    
    def create_destination(
        self,
        name: str,
        account_url: str,
        warehouse: str,
        database_name: str,
        database_user: str,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake",
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new Snowflake destination with key-pair authentication.
        
        Args:
            name: Name for the destination
            account_url: Snowflake account URL
            warehouse: Snowflake warehouse name
            database_name: Target database name
            database_user: Snowflake username
            private_key: Private key content (PEM format)
            private_key_passphrase: Passphrase if key is encrypted
            connector_id: Connector type (default: 'snowflake', used in v1 only)
            region: AWS region for Snowflake (required for v2.0 API, e.g., 'us-west-2')
            
        Returns:
            API response containing destination details including ID
            
        Raises:
            HevoClientError: If destination creation fails
        """
        payload = self._build_create_payload(
            name=name,
            account_url=account_url,
            warehouse=warehouse,
            database_name=database_name,
            database_user=database_user,
            private_key=private_key,
            private_key_passphrase=private_key_passphrase,
            connector_id=connector_id,
            region=region
        )
        
        url = self._get_url("destinations")
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                auth=self.auth
            )
            result = self._handle_response(response)
            print(f"Successfully created destination: {name} (API {self.api_version})")
            return result
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")
    
    def _build_update_payload(
        self,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake",
        account_url: Optional[str] = None,
        warehouse: Optional[str] = None,
        database_name: Optional[str] = None,
        database_user: Optional[str] = None,
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build the update destination payload based on API version.
        
        v2.0 requires full config including account_name, region, etc.
        v1 only needs the updated fields.
        """
        # Strip leading/trailing whitespace from private key
        clean_private_key = private_key.strip() if private_key else private_key
        
        if self.api_version == "v2.0":
            # v2.0 API requires full config for PUT updates
            region_value = region if region else self._extract_region(account_url) if account_url else 'us-west-2'
            config = {
                "authentication_type": "KEY_PAIR",
                "account_name": self._extract_account_name(account_url) if account_url else "",
                "region": region_value,
                "warehouse": warehouse or "",
                "db_name": database_name or "",
                "db_user": database_user or "",
                "private_key": clean_private_key
            }
            
            if private_key_passphrase:
                config["private_key_passphrase"] = private_key_passphrase
            
            payload = {
                "config": config
            }
        else:
            # v1 API schema (Production) - only needs updated fields
            config = {
                "authentication_type": "PRIVATE_KEY",
                "private_key": clean_private_key
            }
            
            if private_key_passphrase:
                config["private_key_passphrase"] = private_key_passphrase
            
            payload = {
                "config": config,
                "connector_id": connector_id
            }
        
        return payload
    
    def update_destination(
        self,
        destination_id: str,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake",
        account_url: Optional[str] = None,
        warehouse: Optional[str] = None,
        database_name: Optional[str] = None,
        database_user: Optional[str] = None,
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an existing Snowflake destination with a new private key.
        
        Used during key rotation to update the destination with the new key.
        
        Args:
            destination_id: ID of the destination to update
            private_key: New private key content (PEM format)
            private_key_passphrase: Passphrase if key is encrypted
            connector_id: Connector type (default: 'snowflake', used in v1 only)
            account_url: Snowflake account URL (required for v2.0)
            warehouse: Snowflake warehouse (required for v2.0)
            database_name: Database name (required for v2.0)
            database_user: Database user (required for v2.0)
            region: AWS region (required for v2.0)
            
        Returns:
            API response with update confirmation
            
        Raises:
            HevoClientError: If destination update fails
        """
        payload = self._build_update_payload(
            private_key=private_key,
            private_key_passphrase=private_key_passphrase,
            connector_id=connector_id,
            account_url=account_url,
            warehouse=warehouse,
            database_name=database_name,
            database_user=database_user,
            region=region
        )
        
        url = self._get_url(f"destinations/{destination_id}")
        
        try:
            # v2.0 API uses PUT, v1 uses PATCH
            if self.api_version == "v2.0":
                response = requests.put(
                    url,
                    json=payload,
                    headers=self.headers,
                    auth=self.auth
                )
            else:
                response = requests.patch(
                    url,
                    json=payload,
                    headers=self.headers,
                    auth=self.auth
                )
            result = self._handle_response(response)
            print(f"Successfully updated destination: {destination_id} (API {self.api_version})")
            return result
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")
    
    def get_destination(self, destination_id: str) -> Dict[str, Any]:
        """
        Get details of a specific destination.
        
        Args:
            destination_id: ID of the destination to retrieve
            
        Returns:
            Destination details
            
        Raises:
            HevoClientError: If retrieval fails
        """
        url = self._get_url(f"destinations/{destination_id}")
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                auth=self.auth
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")
    
    def list_destinations(self) -> Dict[str, Any]:
        """
        List all destinations in the account.
        
        Returns:
            List of destinations
            
        Raises:
            HevoClientError: If listing fails
        """
        url = self._get_url("destinations")
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                auth=self.auth
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")
    
    def test_destination(self, destination_id: str) -> Dict[str, Any]:
        """
        Test connection for a destination.
        
        Args:
            destination_id: ID of the destination to test
            
        Returns:
            Test result
            
        Raises:
            HevoClientError: If test fails
        """
        url = self._get_url(f"destinations/{destination_id}/test")
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                auth=self.auth
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")


if __name__ == "__main__":
    # Example usage (requires valid credentials)
    print("HevoClient module loaded successfully")
    print("Use HevoClient class to manage Hevo destinations via API")
