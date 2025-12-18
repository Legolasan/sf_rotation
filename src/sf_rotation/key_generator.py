"""
Key Generator Module

Generates RSA key pairs for Snowflake authentication using OpenSSL.
Supports both encrypted (DES3) and non-encrypted private keys.
"""

import subprocess
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional


class KeyGenerationError(Exception):
    """Custom exception for key generation errors."""
    pass


class KeyGenerator:
    """
    Generates and manages RSA key pairs for Snowflake authentication.
    
    Uses OpenSSL commands to generate:
    - RSA 2048-bit private key in PKCS#8 format
    - Corresponding public key
    """
    
    def __init__(self, output_directory: str = "./keys"):
        """
        Initialize the key generator.
        
        Args:
            output_directory: Directory to store generated keys
        """
        self.output_directory = Path(output_directory)
        self._ensure_output_directory()
    
    def _ensure_output_directory(self) -> None:
        """Create the output directory if it doesn't exist."""
        self.output_directory.mkdir(parents=True, exist_ok=True)
    
    def _backup_existing_keys(self, key_name: str) -> Optional[str]:
        """
        Backup existing keys if they exist before generating new ones.
        
        Args:
            key_name: Base name of the key files to backup
            
        Returns:
            Path to backup directory if keys were backed up, None otherwise
        """
        private_key = self.output_directory / f"{key_name}.p8"
        public_key = self.output_directory / f"{key_name}.pub"
        
        if private_key.exists() or public_key.exists():
            # Create backup directory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.output_directory / "backups" / timestamp
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Move existing keys to backup
            if private_key.exists():
                shutil.move(str(private_key), str(backup_dir / private_key.name))
            if public_key.exists():
                shutil.move(str(public_key), str(backup_dir / public_key.name))
            
            return str(backup_dir)
        return None
    
    def _run_command(self, command: str, input_data: Optional[bytes] = None) -> bytes:
        """
        Execute a shell command and return its output.
        
        Args:
            command: Shell command to execute
            input_data: Optional input to pipe to the command
            
        Returns:
            Command output as bytes
            
        Raises:
            KeyGenerationError: If command fails
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                input=input_data,
                capture_output=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise KeyGenerationError(
                f"Command failed: {command}\nError: {e.stderr.decode()}"
            )
    
    def generate_private_key(
        self,
        key_name: str = "rsa_key",
        encrypted: bool = False,
        passphrase: Optional[str] = None
    ) -> Path:
        """
        Generate an RSA private key in PKCS#8 format.
        
        Args:
            key_name: Base name for the key file (without extension)
            encrypted: Whether to encrypt the private key with DES3
            passphrase: Passphrase for encrypted key (required if encrypted=True)
            
        Returns:
            Path to the generated private key file
            
        Raises:
            KeyGenerationError: If key generation fails
            ValueError: If encrypted=True but no passphrase provided
        """
        if encrypted and not passphrase:
            raise ValueError("Passphrase is required for encrypted keys")
        
        private_key_path = self.output_directory / f"{key_name}.p8"
        
        if encrypted:
            # Generate encrypted private key with DES3
            command = (
                f"openssl genrsa 2048 | "
                f"openssl pkcs8 -topk8 -v2 des3 -inform PEM "
                f"-out {private_key_path} -passout pass:{passphrase}"
            )
        else:
            # Generate non-encrypted private key
            command = (
                f"openssl genrsa 2048 | "
                f"openssl pkcs8 -topk8 -inform PEM "
                f"-out {private_key_path} -nocrypt"
            )
        
        self._run_command(command)
        
        if not private_key_path.exists():
            raise KeyGenerationError(f"Private key was not created at {private_key_path}")
        
        # Set restrictive permissions on the private key
        os.chmod(private_key_path, 0o600)
        
        return private_key_path
    
    def generate_public_key(
        self,
        private_key_path: Path,
        passphrase: Optional[str] = None
    ) -> Path:
        """
        Generate a public key from a private key.
        
        Args:
            private_key_path: Path to the private key file
            passphrase: Passphrase if the private key is encrypted
            
        Returns:
            Path to the generated public key file
            
        Raises:
            KeyGenerationError: If public key generation fails
        """
        private_key_path = Path(private_key_path)
        public_key_path = private_key_path.with_suffix('.pub')
        
        if passphrase:
            command = (
                f"openssl rsa -in {private_key_path} -pubout "
                f"-out {public_key_path} -passin pass:{passphrase}"
            )
        else:
            command = (
                f"openssl rsa -in {private_key_path} -pubout "
                f"-out {public_key_path}"
            )
        
        self._run_command(command)
        
        if not public_key_path.exists():
            raise KeyGenerationError(f"Public key was not created at {public_key_path}")
        
        return public_key_path
    
    def generate_key_pair(
        self,
        key_name: str = "rsa_key",
        encrypted: bool = False,
        passphrase: Optional[str] = None,
        backup_existing: bool = True
    ) -> Tuple[Path, Path, Optional[str]]:
        """
        Generate a complete RSA key pair (private and public keys).
        
        Args:
            key_name: Base name for the key files
            encrypted: Whether to encrypt the private key
            passphrase: Passphrase for encrypted key
            backup_existing: Whether to backup existing keys before generating
            
        Returns:
            Tuple of (private_key_path, public_key_path, backup_path or None)
        """
        # Backup existing keys if requested
        backup_path = None
        if backup_existing:
            backup_path = self._backup_existing_keys(key_name)
        
        private_key_path = self.generate_private_key(
            key_name=key_name,
            encrypted=encrypted,
            passphrase=passphrase
        )
        
        public_key_path = self.generate_public_key(
            private_key_path=private_key_path,
            passphrase=passphrase
        )
        
        return private_key_path, public_key_path, backup_path
    
    @staticmethod
    def read_private_key(private_key_path: Path) -> str:
        """
        Read the private key content from file.
        
        Args:
            private_key_path: Path to the private key file
            
        Returns:
            Private key content as string
        """
        with open(private_key_path, 'r') as f:
            return f.read()
    
    @staticmethod
    def read_public_key(public_key_path: Path) -> str:
        """
        Read the public key content from file.
        
        Args:
            public_key_path: Path to the public key file
            
        Returns:
            Public key content as string
        """
        with open(public_key_path, 'r') as f:
            return f.read()
    
    @staticmethod
    def format_public_key_for_snowflake(public_key_content: str) -> str:
        """
        Format public key for Snowflake ALTER USER command.
        
        Removes the PEM header/footer and joins lines into a single string.
        
        Args:
            public_key_content: Raw public key content with PEM headers
            
        Returns:
            Formatted public key string for Snowflake
        """
        # Remove header, footer, and newlines
        lines = public_key_content.strip().split('\n')
        # Filter out PEM header and footer lines
        key_lines = [
            line for line in lines 
            if not line.startswith('-----')
        ]
        return ''.join(key_lines)
    
    @staticmethod
    def is_key_encrypted(private_key_path: Path) -> bool:
        """
        Check if a private key is encrypted.
        
        Args:
            private_key_path: Path to the private key file
            
        Returns:
            True if key is encrypted, False otherwise
        """
        with open(private_key_path, 'r') as f:
            content = f.read()
        return 'ENCRYPTED' in content


if __name__ == "__main__":
    # Example usage
    generator = KeyGenerator(output_directory="./keys")
    
    # Generate non-encrypted key pair
    print("Generating non-encrypted key pair...")
    priv_path, pub_path = generator.generate_key_pair(
        key_name="test_key",
        encrypted=False
    )
    print(f"Private key: {priv_path}")
    print(f"Public key: {pub_path}")
    
    # Read and format public key for Snowflake
    pub_content = generator.read_public_key(pub_path)
    formatted_key = generator.format_public_key_for_snowflake(pub_content)
    print(f"\nFormatted public key for Snowflake:\n{formatted_key[:50]}...")
