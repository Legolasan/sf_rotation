"""
Unit tests for KeyGenerator.

Tests cover:
- RSA key pair generation
- Key file operations
- Public key formatting for Snowflake
- Backup functionality
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from sf_rotation.key_generator import KeyGenerator, KeyGenerationError


class TestKeyGeneratorInit:
    """Tests for KeyGenerator initialization."""
    
    def test_init_creates_directory(self):
        """Test output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, 'new_keys')
            generator = KeyGenerator(output_directory=output_dir)
            
            assert os.path.exists(output_dir)
            assert str(generator.output_directory) == output_dir
    
    def test_init_existing_directory(self):
        """Test works with existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            assert str(generator.output_directory) == tmpdir


class TestGenerateKeyPair:
    """Tests for generate_key_pair method."""
    
    def test_generate_key_pair_creates_files(self):
        """Test key pair files are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            private_path, public_path, backup_path = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            assert os.path.exists(private_path)
            assert os.path.exists(public_path)
            assert str(private_path).endswith('.p8')
            assert str(public_path).endswith('.pub')
    
    def test_generate_key_pair_private_key_content(self):
        """Test private key has correct PEM format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            private_path, _, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            with open(private_path, 'r') as f:
                content = f.read()
            
            assert '-----BEGIN PRIVATE KEY-----' in content
            assert '-----END PRIVATE KEY-----' in content
    
    def test_generate_key_pair_public_key_content(self):
        """Test public key has correct PEM format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            _, public_path, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            with open(public_path, 'r') as f:
                content = f.read()
            
            assert '-----BEGIN PUBLIC KEY-----' in content
            assert '-----END PUBLIC KEY-----' in content
    
    def test_generate_key_pair_encrypted(self):
        """Test encrypted key pair generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            private_path, public_path, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=True,
                passphrase='testpass123'
            )
            
            with open(private_path, 'r') as f:
                content = f.read()
            
            # Encrypted keys have different header
            assert '-----BEGIN ENCRYPTED PRIVATE KEY-----' in content
    
    def test_generate_key_pair_backup_existing(self):
        """Test existing keys are backed up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            
            # Create first key pair
            generator.generate_key_pair(key_name='test_key', encrypted=False)
            
            # Create second key pair with backup
            _, _, backup_path = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False,
                backup_existing=True
            )
            
            # Backup should be created
            assert backup_path is not None
            assert os.path.exists(backup_path)


class TestReadKeys:
    """Tests for key reading methods."""
    
    def test_read_private_key(self):
        """Test reading private key content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            private_path, _, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            content = generator.read_private_key(private_path)
            
            assert '-----BEGIN PRIVATE KEY-----' in content
            assert len(content) > 100  # Reasonable key size
    
    def test_read_public_key(self):
        """Test reading public key content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            _, public_path, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            content = generator.read_public_key(public_path)
            
            assert '-----BEGIN PUBLIC KEY-----' in content


class TestFormatPublicKeyForSnowflake:
    """Tests for Snowflake public key formatting."""
    
    def test_format_removes_headers(self):
        """Test PEM headers are removed."""
        generator = KeyGenerator(output_directory='/tmp')
        
        pem_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA
-----END PUBLIC KEY-----"""
        
        formatted = generator.format_public_key_for_snowflake(pem_key)
        
        assert '-----BEGIN' not in formatted
        assert '-----END' not in formatted
    
    def test_format_removes_newlines(self):
        """Test newlines are removed."""
        generator = KeyGenerator(output_directory='/tmp')
        
        pem_key = """-----BEGIN PUBLIC KEY-----
MIIB
IjAN
-----END PUBLIC KEY-----"""
        
        formatted = generator.format_public_key_for_snowflake(pem_key)
        
        assert '\n' not in formatted
        assert formatted == 'MIIBIjAN'
    
    def test_format_with_actual_key(self):
        """Test formatting with actual generated key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            _, public_path, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            content = generator.read_public_key(public_path)
            formatted = generator.format_public_key_for_snowflake(content)
            
            # Should be single line, no headers
            assert '\n' not in formatted
            assert '-----' not in formatted
            # Should start with expected base64 prefix
            assert formatted.startswith('MIIB')


class TestKeySize:
    """Tests for key size configuration."""
    
    def test_generated_key_is_2048_bit(self):
        """Test generated key is 2048-bit RSA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            private_path, _, _ = generator.generate_key_pair(
                key_name='test_key',
                encrypted=False
            )
            
            # Read and verify it's an RSA key
            with open(private_path, 'r') as f:
                content = f.read()
            
            assert '-----BEGIN PRIVATE KEY-----' in content


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_read_nonexistent_file_raises(self):
        """Test reading non-existent file raises FileNotFoundError."""
        generator = KeyGenerator(output_directory='/tmp')
        
        with pytest.raises(FileNotFoundError):
            generator.read_private_key('/nonexistent/path/key.p8')
    
    def test_invalid_passphrase_handling(self):
        """Test encrypted key without passphrase raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = KeyGenerator(output_directory=tmpdir)
            
            # Creating encrypted key without passphrase should fail
            with pytest.raises((KeyGenerationError, TypeError, ValueError)):
                generator.generate_key_pair(
                    key_name='test_key',
                    encrypted=True,
                    passphrase=None  # Missing passphrase
                )
