"""
Snowflake Client Module

Manages Snowflake connections and RSA public key configuration for users.
Uses username/password authentication to set up key-pair authentication.
"""

import snowflake.connector
from typing import Optional
from contextlib import contextmanager


class SnowflakeClientError(Exception):
    """Custom exception for Snowflake client errors."""
    pass


class SnowflakeClient:
    """
    Client for managing Snowflake connections and user RSA key configuration.
    
    Connects using username/password and provides methods to set/unset
    RSA public keys for key-pair authentication.
    """
    
    def __init__(
        self,
        account_url: str,
        username: str,
        password: str,
        warehouse: Optional[str] = None,
        database: Optional[str] = None,
        role: Optional[str] = None
    ):
        """
        Initialize the Snowflake client.
        
        Args:
            account_url: Snowflake account URL (e.g., 'account.snowflakecomputing.com')
            username: Snowflake username for authentication
            password: Snowflake password for authentication
            warehouse: Optional warehouse to use
            database: Optional database to use
            role: Optional role to use
        """
        # Extract account identifier from URL
        self.account = self._extract_account(account_url)
        self.username = username
        self.password = password
        self.warehouse = warehouse
        self.database = database
        self.role = role
        self._connection = None
    
    @staticmethod
    def _extract_account(account_url: str) -> str:
        """
        Extract account identifier from account URL.
        
        Args:
            account_url: Full account URL or account identifier
            
        Returns:
            Account identifier for Snowflake connector
        """
        # Remove protocol if present
        account = account_url.replace('https://', '').replace('http://', '')
        # Remove .snowflakecomputing.com suffix if present
        account = account.replace('.snowflakecomputing.com', '')
        return account
    
    @contextmanager
    def connection(self):
        """
        Context manager for Snowflake connection.
        
        Yields:
            Active Snowflake connection
            
        Example:
            with client.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
        """
        conn = None
        try:
            conn = snowflake.connector.connect(
                account=self.account,
                user=self.username,
                password=self.password,
                warehouse=self.warehouse,
                database=self.database,
                role=self.role
            )
            yield conn
        except snowflake.connector.errors.Error as e:
            raise SnowflakeClientError(f"Connection failed: {e}")
        finally:
            if conn:
                conn.close()
    
    def test_connection(self) -> bool:
        """
        Test the Snowflake connection.
        
        Returns:
            True if connection successful
            
        Raises:
            SnowflakeClientError: If connection fails
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT CURRENT_USER(), CURRENT_ACCOUNT()")
            result = cursor.fetchone()
            print(f"Connected as user: {result[0]}, account: {result[1]}")
            return True
    
    def set_rsa_public_key(self, user: str, public_key: str) -> None:
        """
        Set RSA_PUBLIC_KEY for a user.
        
        This is typically used for initial key setup.
        
        Args:
            user: Username to set the public key for
            public_key: Formatted public key (without PEM headers)
            
        Raises:
            SnowflakeClientError: If the operation fails
        """
        self._set_key(user, public_key, key_number=1)
    
    def set_rsa_public_key_2(self, user: str, public_key: str) -> None:
        """
        Set RSA_PUBLIC_KEY_2 for a user.
        
        This is typically used during key rotation to set the new key
        before removing the old one.
        
        Args:
            user: Username to set the public key for
            public_key: Formatted public key (without PEM headers)
            
        Raises:
            SnowflakeClientError: If the operation fails
        """
        self._set_key(user, public_key, key_number=2)
    
    def _set_key(self, user: str, public_key: str, key_number: int) -> None:
        """
        Internal method to set RSA public key.
        
        Args:
            user: Username to set the public key for
            public_key: Formatted public key
            key_number: 1 for RSA_PUBLIC_KEY, 2 for RSA_PUBLIC_KEY_2
        """
        key_field = "RSA_PUBLIC_KEY" if key_number == 1 else "RSA_PUBLIC_KEY_2"
        
        # Ensure public key doesn't contain newlines or extra whitespace
        clean_key = public_key.strip().replace('\n', '').replace('\r', '')
        
        query = f"ALTER USER {user} SET {key_field}='{clean_key}'"
        
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                print(f"Successfully set {key_field} for user {user}")
        except Exception as e:
            raise SnowflakeClientError(f"Failed to set {key_field} for user {user}: {e}")
    
    def unset_rsa_public_key(self, user: str) -> None:
        """
        Unset RSA_PUBLIC_KEY for a user.
        
        Args:
            user: Username to unset the public key for
            
        Raises:
            SnowflakeClientError: If the operation fails
        """
        self._unset_key(user, key_number=1)
    
    def unset_rsa_public_key_2(self, user: str) -> None:
        """
        Unset RSA_PUBLIC_KEY_2 for a user.
        
        Args:
            user: Username to unset the public key for
            
        Raises:
            SnowflakeClientError: If the operation fails
        """
        self._unset_key(user, key_number=2)
    
    def _unset_key(self, user: str, key_number: int) -> None:
        """
        Internal method to unset RSA public key.
        
        Args:
            user: Username to unset the public key for
            key_number: 1 for RSA_PUBLIC_KEY, 2 for RSA_PUBLIC_KEY_2
        """
        key_field = "RSA_PUBLIC_KEY" if key_number == 1 else "RSA_PUBLIC_KEY_2"
        
        query = f"ALTER USER {user} UNSET {key_field}"
        
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                print(f"Successfully unset {key_field} for user {user}")
        except Exception as e:
            raise SnowflakeClientError(f"Failed to unset {key_field} for user {user}: {e}")
    
    def get_user_public_keys(self, user: str) -> dict:
        """
        Get the current RSA public key status for a user.
        
        Args:
            user: Username to check
            
        Returns:
            Dictionary with key status information
        """
        query = f"DESCRIBE USER {user}"
        
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                results = cursor.fetchall()
                
                key_info = {
                    'RSA_PUBLIC_KEY': None,
                    'RSA_PUBLIC_KEY_2': None,
                    'RSA_PUBLIC_KEY_FP': None,
                    'RSA_PUBLIC_KEY_2_FP': None
                }
                
                for row in results:
                    property_name = row[0]
                    property_value = row[1]
                    
                    if property_name in key_info:
                        key_info[property_name] = property_value
                
                return key_info
        except Exception as e:
            raise SnowflakeClientError(f"Failed to get user info for {user}: {e}")
    
    def verify_key_setup(self, user: str) -> bool:
        """
        Verify that at least one RSA public key is set for the user.
        
        Args:
            user: Username to verify
            
        Returns:
            True if at least one key is set
        """
        key_info = self.get_user_public_keys(user)
        
        has_key_1 = key_info.get('RSA_PUBLIC_KEY_FP') is not None
        has_key_2 = key_info.get('RSA_PUBLIC_KEY_2_FP') is not None
        
        if has_key_1:
            print(f"User {user} has RSA_PUBLIC_KEY set (fingerprint: {key_info['RSA_PUBLIC_KEY_FP']})")
        if has_key_2:
            print(f"User {user} has RSA_PUBLIC_KEY_2 set (fingerprint: {key_info['RSA_PUBLIC_KEY_2_FP']})")
        
        return has_key_1 or has_key_2


if __name__ == "__main__":
    # Example usage (requires valid credentials)
    print("SnowflakeClient module loaded successfully")
    print("Use SnowflakeClient class to manage Snowflake key-pair authentication")
