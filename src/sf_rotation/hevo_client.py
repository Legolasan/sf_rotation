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
    """
    
    API_VERSION = "v1"
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str
    ):
        """
        Initialize the Hevo API client.
        
        Args:
            base_url: Hevo API base URL (e.g., 'https://us.hevodata.com')
            username: Hevo account username for Basic Auth
            password: Hevo account password for Basic Auth
        """
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def _get_url(self, endpoint: str) -> str:
        """
        Build full API URL for an endpoint.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Full URL string
        """
        return f"{self.base_url}/api/{self.API_VERSION}/{endpoint.lstrip('/')}"
    
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
    
    def create_destination(
        self,
        name: str,
        account_url: str,
        warehouse: str,
        database_name: str,
        database_user: str,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake"
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
            connector_id: Connector type (default: 'snowflake')
            
        Returns:
            API response containing destination details including ID
            
        Raises:
            HevoClientError: If destination creation fails
        """
        # Strip leading/trailing whitespace from private key
        # Hevo API rejects keys with extra whitespace
        clean_private_key = private_key.strip() if private_key else private_key
        
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
        
        url = self._get_url("destinations")
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                auth=self.auth
            )
            result = self._handle_response(response)
            print(f"Successfully created destination: {name}")
            return result
        except requests.RequestException as e:
            raise HevoClientError(f"Request failed: {e}")
    
    def update_destination(
        self,
        destination_id: str,
        private_key: str,
        private_key_passphrase: Optional[str] = None,
        connector_id: str = "snowflake"
    ) -> Dict[str, Any]:
        """
        Update an existing Snowflake destination with a new private key.
        
        Used during key rotation to update the destination with the new key.
        
        Args:
            destination_id: ID of the destination to update
            private_key: New private key content (PEM format)
            private_key_passphrase: Passphrase if key is encrypted
            connector_id: Connector type (default: 'snowflake')
            
        Returns:
            API response with update confirmation
            
        Raises:
            HevoClientError: If destination update fails
        """
        # Strip leading/trailing whitespace from private key
        # Hevo API rejects keys with extra whitespace
        clean_private_key = private_key.strip() if private_key else private_key
        
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
        
        url = self._get_url(f"destinations/{destination_id}")
        
        try:
            response = requests.patch(
                url,
                json=payload,
                headers=self.headers,
                auth=self.auth
            )
            result = self._handle_response(response)
            print(f"Successfully updated destination: {destination_id}")
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
