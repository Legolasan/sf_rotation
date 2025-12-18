#!/usr/bin/env python3
"""
Snowflake Key Pair Rotation Tool

Main orchestrator script for setting up and rotating Snowflake key-pair
authentication with Hevo Data destinations.

Usage:
    sf-rotation --help                                   # Show all commands
    sf-rotation setup --help                             # Setup command help
    sf-rotation setup --config config/config.yaml        # New destination
    sf-rotation update-keys --config config/config.yaml  # Existing destination
    sf-rotation rotate --config config/config.yaml       # Key rotation
    sf-rotation setup --config config/config.yaml --encrypted  # With encryption
"""

import argparse
import sys
from pathlib import Path

from .key_generator import KeyGenerator, KeyGenerationError
from .snowflake_client import SnowflakeClient, SnowflakeClientError
from .hevo_client import HevoClient, HevoClientError
from .utils import (
    load_config,
    save_config,
    validate_config,
    get_passphrase,
    backup_keys,
    setup_logging,
    print_banner,
    print_step,
    print_success,
    print_error,
    print_warning,
    print_info,
    confirm_action,
    format_key_for_display
)


def run_setup(config: dict, config_path: str, encrypted: bool = False) -> bool:
    """
    Run the initial key pair setup process.
    
    Steps:
    1. Generate key pair
    2. Connect to Snowflake
    3. Set RSA_PUBLIC_KEY for user
    4. Create Hevo destination with private key
    5. Save destination_id to config file
    
    Args:
        config: Configuration dictionary
        config_path: Path to the configuration file (for auto-saving destination_id)
        encrypted: Whether to use encrypted private key
        
    Returns:
        True if setup successful, False otherwise
    """
    print_banner()
    print_info("Starting INITIAL SETUP process")
    
    # Get configuration values
    sf_config = config['snowflake']
    hevo_config = config['hevo']
    keys_config = config['keys']
    
    # Check if destination already exists in config
    existing_destination_id = hevo_config.get('destination_id')
    if existing_destination_id and str(existing_destination_id).strip():
        print_warning(f"A destination_id ({existing_destination_id}) already exists in your config!")
        print_info("This means you already have a Hevo destination configured.")
        print_info("")
        print_info("Recommended actions:")
        print_info("  - To rotate keys: sf-rotation rotate --config <config>")
        print_info("  - To update existing destination: sf-rotation update-keys --config <config>")
        print_info("")
        
        if not confirm_action("Do you want to CREATE A NEW destination anyway? (This will replace the existing destination_id in config)"):
            print_info("Setup cancelled. Use 'rotate' or 'update-keys' for existing destinations.")
            return False
        
        print_warning("Proceeding to create NEW destination...")
    
    keys_dir = keys_config.get('output_directory', './keys')
    passphrase = None
    
    # Handle encryption/passphrase
    if encrypted or keys_config.get('encrypted'):
        encrypted = True
        passphrase = keys_config.get('passphrase')
        if not passphrase:
            passphrase = get_passphrase("Enter passphrase for private key encryption: ")
            confirm_passphrase = get_passphrase("Confirm passphrase: ")
            if passphrase != confirm_passphrase:
                print_error("Passphrases do not match!")
                return False
    
    try:
        # Step 1: Generate key pair (with automatic backup of existing keys)
        print_step(1, "Generating RSA key pair")
        
        key_generator = KeyGenerator(output_directory=keys_dir)
        private_key_path, public_key_path, backup_path = key_generator.generate_key_pair(
            key_name="rsa_key",
            encrypted=encrypted,
            passphrase=passphrase,
            backup_existing=True
        )
        
        if backup_path:
            print_warning(f"Existing keys backed up to: {backup_path}")
        
        print_info(f"Private key saved to: {private_key_path}")
        print_info(f"Public key saved to: {public_key_path}")
        
        # Read and format keys
        private_key_content = key_generator.read_private_key(private_key_path)
        public_key_content = key_generator.read_public_key(public_key_path)
        formatted_public_key = key_generator.format_public_key_for_snowflake(public_key_content)
        
        print_success("Key pair generated successfully")
        
        # Step 2: Connect to Snowflake
        print_step(2, "Connecting to Snowflake")
        
        sf_client = SnowflakeClient(
            account_url=sf_config['account_url'],
            username=sf_config['username'],
            password=sf_config['password'],
            warehouse=sf_config.get('warehouse'),
            database=sf_config.get('database')
        )
        
        sf_client.test_connection()
        print_success("Connected to Snowflake successfully")
        
        # Step 3: Check available key slot and set public key
        print_step(3, f"Setting RSA public key for user: {sf_config['user_to_modify']}")
        
        # Check which key slot is available
        key_slot = sf_client.get_available_key_slot(sf_config['user_to_modify'])
        
        if key_slot == 0:
            print_error("Both RSA_PUBLIC_KEY and RSA_PUBLIC_KEY_2 are already set for this user")
            print_info("Run 'rotate' mode to rotate keys, or manually UNSET one of the keys:")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY;")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY_2;")
            return False
        elif key_slot == 2:
            print_warning("RSA_PUBLIC_KEY already set, using RSA_PUBLIC_KEY_2 instead")
            sf_client.set_rsa_public_key_2(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        else:
            sf_client.set_rsa_public_key(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        
        # Verify key was set
        sf_client.verify_key_setup(sf_config['user_to_modify'])
        print_success("RSA public key set successfully in Snowflake")
        
        # Step 4: Create Hevo destination
        print_step(4, "Creating Hevo destination with key-pair authentication")
        
        hevo_client = HevoClient(
            base_url=hevo_config['base_url'],
            username=hevo_config['username'],
            password=hevo_config['password']
        )
        
        result = hevo_client.create_destination(
            name=hevo_config['destination_name'],
            account_url=sf_config['account_url'],
            warehouse=sf_config.get('warehouse', ''),
            database_name=sf_config.get('database', ''),
            database_user=sf_config['user_to_modify'],
            private_key=private_key_content,
            private_key_passphrase=passphrase
        )
        
        # Extract destination_id from response
        destination_id = result.get('id') or result.get('destination_id') or result.get('data', {}).get('id')
        
        if destination_id:
            print_info(f"Destination ID: {destination_id}")
            
            # Step 5: Save destination_id to config file
            print_step(5, "Saving destination ID to configuration file")
            config['hevo']['destination_id'] = str(destination_id)
            save_config(config, config_path)
            print_success(f"Destination ID saved to {config_path}")
        
        print_success("Hevo destination created successfully")
        
        print("\n" + "="*60)
        print("SETUP COMPLETE!")
        print("="*60)
        print(f"\nKey files location: {keys_dir}/")
        print(f"  - Private key: rsa_key.p8")
        print(f"  - Public key: rsa_key.pub")
        if destination_id:
            print(f"\nHevo Destination ID: {destination_id}")
            print(f"(Automatically saved to {config_path})")
        
        return True
        
    except KeyGenerationError as e:
        print_error(f"Key generation failed: {e}")
        return False
    except SnowflakeClientError as e:
        print_error(f"Snowflake operation failed: {e}")
        return False
    except HevoClientError as e:
        print_error(f"Hevo API operation failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def run_rotate(config: dict, config_path: str, encrypted: bool = False) -> bool:
    """
    Run the key rotation process.
    
    Steps:
    1. Backup existing keys
    2. Generate new key pair
    3. Connect to Snowflake
    4. Set RSA_PUBLIC_KEY_2 with new key
    5. Update Hevo destination with new private key
    6. On success, unset RSA_PUBLIC_KEY (old key)
    
    Args:
        config: Configuration dictionary
        config_path: Path to the configuration file
        encrypted: Whether to use encrypted private key
        
    Returns:
        True if rotation successful, False otherwise
    """
    print_banner()
    print_info("Starting KEY ROTATION process")
    
    # Get configuration values
    sf_config = config['snowflake']
    hevo_config = config['hevo']
    keys_config = config['keys']
    
    keys_dir = keys_config.get('output_directory', './keys')
    passphrase = None
    
    # Verify destination_id is configured
    destination_id = hevo_config.get('destination_id')
    if not destination_id:
        print_error("destination_id is not set in config. Run 'setup' first or add it manually.")
        return False
    
    # Handle encryption/passphrase
    if encrypted or keys_config.get('encrypted'):
        encrypted = True
        passphrase = keys_config.get('passphrase')
        if not passphrase:
            passphrase = get_passphrase("Enter passphrase for new private key encryption: ")
            confirm_passphrase = get_passphrase("Confirm passphrase: ")
            if passphrase != confirm_passphrase:
                print_error("Passphrases do not match!")
                return False
    
    try:
        # Step 1: Backup existing keys
        print_step(1, "Backing up existing keys")
        
        backup_path = backup_keys(keys_dir)
        if backup_path:
            print_info(f"Existing keys backed up to: {backup_path}")
        else:
            print_warning("No existing keys found to backup")
        
        # Step 2: Generate new key pair
        print_step(2, "Generating new RSA key pair")
        
        key_generator = KeyGenerator(output_directory=keys_dir)
        
        # Use new_rsa_key as name to differentiate during rotation
        # Don't backup since we're using a different key name
        private_key_path, public_key_path, _ = key_generator.generate_key_pair(
            key_name="new_rsa_key",
            encrypted=encrypted,
            passphrase=passphrase,
            backup_existing=False
        )
        
        print_info(f"New private key saved to: {private_key_path}")
        print_info(f"New public key saved to: {public_key_path}")
        
        # Read and format keys
        private_key_content = key_generator.read_private_key(private_key_path)
        public_key_content = key_generator.read_public_key(public_key_path)
        formatted_public_key = key_generator.format_public_key_for_snowflake(public_key_content)
        
        print_success("New key pair generated successfully")
        
        # Step 3: Connect to Snowflake
        print_step(3, "Connecting to Snowflake")
        
        sf_client = SnowflakeClient(
            account_url=sf_config['account_url'],
            username=sf_config['username'],
            password=sf_config['password'],
            warehouse=sf_config.get('warehouse'),
            database=sf_config.get('database')
        )
        
        sf_client.test_connection()
        print_success("Connected to Snowflake successfully")
        
        # Step 4: Detect current key slot and set new key in the OTHER slot
        print_step(4, f"Detecting current key slot for user: {sf_config['user_to_modify']}")
        
        key_info = sf_client.get_user_public_keys(sf_config['user_to_modify'])
        
        # Check if key fingerprint exists and is not empty
        # Snowflake can return: None, empty string '', or literal string 'null'
        key1_fp = key_info.get('RSA_PUBLIC_KEY_FP')
        key2_fp = key_info.get('RSA_PUBLIC_KEY_2_FP')
        key1_set = sf_client._is_key_set(key1_fp)
        key2_set = sf_client._is_key_set(key2_fp)
        
        # Determine which slot has the OLD key and which slot to use for NEW key
        if key1_set and not key2_set:
            # Old key in slot 1 -> New key goes to slot 2
            old_key_slot = 1
            new_key_slot = 2
            print_info("Current key is in RSA_PUBLIC_KEY (slot 1)")
            print_info("New key will be set in RSA_PUBLIC_KEY_2 (slot 2)")
        elif key2_set and not key1_set:
            # Old key in slot 2 -> New key goes to slot 1
            old_key_slot = 2
            new_key_slot = 1
            print_info("Current key is in RSA_PUBLIC_KEY_2 (slot 2)")
            print_info("New key will be set in RSA_PUBLIC_KEY (slot 1)")
        elif key1_set and key2_set:
            # Both slots occupied - cannot rotate safely
            print_error("Both RSA_PUBLIC_KEY and RSA_PUBLIC_KEY_2 are set!")
            print_info("Cannot perform safe rotation. Please manually unset one key first:")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY;")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY_2;")
            return False
        else:
            # No keys set - should use setup instead
            print_error("No RSA public keys are currently set for this user.")
            print_info("Run 'setup' or 'update-keys' first to configure key-pair authentication.")
            return False
        
        # Set new key in the appropriate slot
        print_step(5, f"Setting new key in RSA_PUBLIC_KEY{'_2' if new_key_slot == 2 else ''}")
        
        if new_key_slot == 2:
            sf_client.set_rsa_public_key_2(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        else:
            sf_client.set_rsa_public_key(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        
        print_success(f"New key set in RSA_PUBLIC_KEY{'_2' if new_key_slot == 2 else ''} successfully")
        
        # Step 6: Update Hevo destination with new private key
        print_step(6, f"Updating Hevo destination (ID: {destination_id}) with new private key")
        
        hevo_client = HevoClient(
            base_url=hevo_config['base_url'],
            username=hevo_config['username'],
            password=hevo_config['password']
        )
        
        hevo_client.update_destination(
            destination_id=destination_id,
            private_key=private_key_content,
            private_key_passphrase=passphrase
        )
        
        print_success("Hevo destination updated with new private key")
        
        # Step 7: Unset old key from the previous slot
        old_key_name = f"RSA_PUBLIC_KEY{'_2' if old_key_slot == 2 else ''}"
        print_step(7, f"Unsetting old {old_key_name} for user: {sf_config['user_to_modify']}")
        
        if confirm_action(f"Confirm: Unset the old {old_key_name}? (This completes the rotation)"):
            if old_key_slot == 1:
                sf_client.unset_rsa_public_key(sf_config['user_to_modify'])
            else:
                sf_client.unset_rsa_public_key_2(sf_config['user_to_modify'])
            print_success(f"Old {old_key_name} unset successfully")
        else:
            print_warning("Skipped unsetting old key. You may need to do this manually later.")
            print_info(f"Command: ALTER USER <user> UNSET {old_key_name};")
        
        # Verify final state
        print_info("Verifying final key configuration...")
        sf_client.verify_key_setup(sf_config['user_to_modify'])
        
        # Rename new keys to standard names
        print_step(8, "Finalizing key files")
        
        import shutil
        from pathlib import Path
        
        keys_path = Path(keys_dir)
        
        # Remove old keys (they're backed up)
        old_private = keys_path / "rsa_key.p8"
        old_public = keys_path / "rsa_key.pub"
        
        if old_private.exists():
            old_private.unlink()
        if old_public.exists():
            old_public.unlink()
        
        # Rename new keys to standard names
        new_private = keys_path / "new_rsa_key.p8"
        new_public = keys_path / "new_rsa_key.pub"
        
        if new_private.exists():
            shutil.move(new_private, old_private)
        if new_public.exists():
            shutil.move(new_public, old_public)
        
        print_success("Key files renamed to standard names")
        
        print("\n" + "="*60)
        print("KEY ROTATION COMPLETE!")
        print("="*60)
        print(f"\nNew key files location: {keys_dir}/")
        print(f"  - Private key: rsa_key.p8")
        print(f"  - Public key: rsa_key.pub")
        print(f"\nBackup location: {backup_path}")
        
        return True
        
    except KeyGenerationError as e:
        print_error(f"Key generation failed: {e}")
        return False
    except SnowflakeClientError as e:
        print_error(f"Snowflake operation failed: {e}")
        print_warning("Rotation may be incomplete. Check Snowflake user configuration.")
        return False
    except HevoClientError as e:
        print_error(f"Hevo API operation failed: {e}")
        print_warning("New key is set in Snowflake but Hevo update failed.")
        print_info("You may need to manually update Hevo or rollback Snowflake key changes.")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def run_update_keys(config: dict, config_path: str, encrypted: bool = False) -> bool:
    """
    Update keys for an existing Hevo destination.
    
    Use this when you already have a Hevo destination (created via UI or API)
    and want to set up or update key-pair authentication.
    
    Steps:
    1. Verify destination_id exists in config
    2. Generate new key pair
    3. Connect to Snowflake and set public key
    4. Update Hevo destination with new private key
    
    Args:
        config: Configuration dictionary
        config_path: Path to the configuration file
        encrypted: Whether to use encrypted private key
        
    Returns:
        True if update successful, False otherwise
    """
    print_banner()
    print_info("Starting UPDATE-KEYS process for existing destination")
    
    # Get configuration values
    sf_config = config['snowflake']
    hevo_config = config['hevo']
    keys_config = config['keys']
    
    keys_dir = keys_config.get('output_directory', './keys')
    passphrase = None
    
    # Step 1: Verify destination_id exists
    destination_id = hevo_config.get('destination_id')
    if not destination_id:
        print_error("destination_id is not set in config.")
        print_info("For existing destinations, add 'destination_id' to your config file:")
        print_info("  hevo:")
        print_info("    destination_id: 'your_destination_id'")
        print_info("\nYou can find your destination ID in the Hevo dashboard.")
        return False
    
    print_info(f"Using existing destination ID: {destination_id}")
    
    # Handle encryption/passphrase
    if encrypted or keys_config.get('encrypted'):
        encrypted = True
        passphrase = keys_config.get('passphrase')
        if not passphrase:
            passphrase = get_passphrase("Enter passphrase for private key encryption: ")
            confirm_passphrase = get_passphrase("Confirm passphrase: ")
            if passphrase != confirm_passphrase:
                print_error("Passphrases do not match!")
                return False
    
    try:
        # Step 2: Generate key pair (with automatic backup of existing keys)
        print_step(1, "Generating RSA key pair")
        
        key_generator = KeyGenerator(output_directory=keys_dir)
        private_key_path, public_key_path, backup_path = key_generator.generate_key_pair(
            key_name="rsa_key",
            encrypted=encrypted,
            passphrase=passphrase,
            backup_existing=True
        )
        
        if backup_path:
            print_warning(f"Existing keys backed up to: {backup_path}")
        
        print_info(f"Private key saved to: {private_key_path}")
        print_info(f"Public key saved to: {public_key_path}")
        
        # Read and format keys
        private_key_content = key_generator.read_private_key(private_key_path)
        public_key_content = key_generator.read_public_key(public_key_path)
        formatted_public_key = key_generator.format_public_key_for_snowflake(public_key_content)
        
        print_success("Key pair generated successfully")
        
        # Step 3: Connect to Snowflake
        print_step(2, "Connecting to Snowflake")
        
        sf_client = SnowflakeClient(
            account_url=sf_config['account_url'],
            username=sf_config['username'],
            password=sf_config['password'],
            warehouse=sf_config.get('warehouse'),
            database=sf_config.get('database')
        )
        
        sf_client.test_connection()
        print_success("Connected to Snowflake successfully")
        
        # Step 4: Check available key slot and set public key
        print_step(3, f"Setting RSA public key for user: {sf_config['user_to_modify']}")
        
        # Check which key slot is available
        key_slot = sf_client.get_available_key_slot(sf_config['user_to_modify'])
        
        if key_slot == 0:
            print_error("Both RSA_PUBLIC_KEY and RSA_PUBLIC_KEY_2 are already set for this user")
            print_info("Run 'rotate' mode to rotate keys, or manually UNSET one of the keys:")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY;")
            print_info("  ALTER USER <user> UNSET RSA_PUBLIC_KEY_2;")
            return False
        elif key_slot == 2:
            print_warning("RSA_PUBLIC_KEY already set, using RSA_PUBLIC_KEY_2 instead")
            sf_client.set_rsa_public_key_2(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        else:
            sf_client.set_rsa_public_key(
                user=sf_config['user_to_modify'],
                public_key=formatted_public_key
            )
        
        # Verify key was set
        sf_client.verify_key_setup(sf_config['user_to_modify'])
        print_success("RSA public key set successfully in Snowflake")
        
        # Step 5: Update Hevo destination with private key
        print_step(4, f"Updating Hevo destination (ID: {destination_id}) with private key")
        
        hevo_client = HevoClient(
            base_url=hevo_config['base_url'],
            username=hevo_config['username'],
            password=hevo_config['password']
        )
        
        hevo_client.update_destination(
            destination_id=destination_id,
            private_key=private_key_content,
            private_key_passphrase=passphrase
        )
        
        print_success("Hevo destination updated with private key")
        
        print("\n" + "="*60)
        print("UPDATE-KEYS COMPLETE!")
        print("="*60)
        print(f"\nKey files location: {keys_dir}/")
        print(f"  - Private key: rsa_key.p8")
        print(f"  - Public key: rsa_key.pub")
        print(f"\nHevo Destination ID: {destination_id}")
        print("\nYour existing Hevo destination is now configured with key-pair authentication.")
        
        return True
        
    except KeyGenerationError as e:
        print_error(f"Key generation failed: {e}")
        return False
    except SnowflakeClientError as e:
        print_error(f"Snowflake operation failed: {e}")
        return False
    except HevoClientError as e:
        print_error(f"Hevo API operation failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='sf-rotation',
        description='''
Snowflake Key Pair Rotation Tool

Automates Snowflake key-pair authentication setup and rotation 
with Hevo Data destinations.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
COMMANDS:
  setup        Create new keys and NEW Hevo destination
  update-keys  Create new keys for EXISTING Hevo destination  
  rotate       Rotate keys (can run multiple times)

QUICK START:
  1. Install:     pip install sf-rotation
  2. Config:      Create config/config.yaml with your credentials
  3. Run:         sf-rotation setup --config config/config.yaml

For command-specific help:
  sf-rotation setup --help
  sf-rotation update-keys --help
  sf-rotation rotate --help

Documentation: https://github.com/Legolasan/sf_rotation
        '''
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Setup subcommand
    setup_parser = subparsers.add_parser(
        'setup',
        help='Initial setup - creates new Hevo destination',
        description='''
SETUP - Initial Key Pair Configuration

Use this when you want to CREATE A NEW Hevo destination with 
key-pair authentication.

WHAT IT DOES:
  1. Generates RSA key pair (saves to ./keys/)
  2. Connects to Snowflake with admin credentials
  3. Sets RSA_PUBLIC_KEY for target user
  4. Creates NEW Hevo destination via API
  5. Auto-saves destination_id to config file

PREREQUISITES:
  - Snowflake admin credentials (to ALTER USER)
  - Hevo API credentials
  - OpenSSL installed
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
EXAMPLES:
  sf-rotation setup --config config/config.yaml
  sf-rotation setup --config config/config.yaml --encrypted
        '''
    )
    
    # Update-keys subcommand
    update_parser = subparsers.add_parser(
        'update-keys',
        help='Update keys for existing Hevo destination',
        description='''
UPDATE-KEYS - Configure Existing Hevo Destination

Use this when you ALREADY HAVE a Hevo destination (created via 
Hevo UI or API) and want to configure key-pair authentication.

WHAT IT DOES:
  1. Generates RSA key pair (saves to ./keys/)
  2. Connects to Snowflake with admin credentials
  3. Sets RSA_PUBLIC_KEY for target user
  4. Updates EXISTING Hevo destination via API

PREREQUISITES:
  - destination_id must be set in config file
  - Find it: Hevo Dashboard > Destinations > URL contains ID
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
EXAMPLES:
  sf-rotation update-keys --config config/config.yaml
  sf-rotation update-keys --config config/config.yaml --encrypted
        '''
    )
    
    # Rotate subcommand
    rotate_parser = subparsers.add_parser(
        'rotate',
        help='Rotate keys with zero-downtime (repeatable)',
        description='''
ROTATE - Zero-Downtime Key Rotation

Use this for ONGOING KEY ROTATIONS. Can be run MULTIPLE TIMES 
without conflicts - automatically alternates between key slots.

WHAT IT DOES:
  1. Backs up current keys to ./keys/backups/
  2. Generates new RSA key pair
  3. Detects current key slot (RSA_PUBLIC_KEY or RSA_PUBLIC_KEY_2)
  4. Sets new key in the OTHER slot (zero-downtime)
  5. Updates Hevo destination with new private key
  6. Unsets the old key slot (after confirmation)

KEY SLOT ALTERNATION:
  Rotate 1: Slot 1 -> Slot 2
  Rotate 2: Slot 2 -> Slot 1
  Rotate 3: Slot 1 -> Slot 2
  ...repeats forever

PREREQUISITES:
  - Must have run 'setup' or 'update-keys' first
  - destination_id must be set in config file
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
EXAMPLES:
  sf-rotation rotate --config config/config.yaml
  sf-rotation rotate --config config/config.yaml --encrypted
        '''
    )
    
    # Add common arguments to each subparser
    for subparser in [setup_parser, update_parser, rotate_parser]:
        subparser.add_argument(
            '--config', '-c',
            required=True,
            metavar='PATH',
            help='Path to configuration YAML file'
        )
        subparser.add_argument(
            '--encrypted', '-e',
            action='store_true',
            help='Use encrypted private key (passphrase prompted at runtime)'
        )
        subparser.add_argument(
            '--log-level',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
            default='INFO',
            help='Logging level (default: INFO)'
        )
    
    args = parser.parse_args()
    
    # Set up logging
    logger = setup_logging(log_level=args.log_level)
    
    # Load and validate configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print_error(f"Configuration file not found: {args.config}")
        print_info("Create a config file based on config/config.yaml.example")
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Validate configuration
    is_valid, errors = validate_config(config)
    if not is_valid:
        print_error("Configuration validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    
    # Execute command
    success = False
    
    if args.command == 'setup':
        success = run_setup(config, config_path=args.config, encrypted=args.encrypted)
    elif args.command == 'rotate':
        success = run_rotate(config, config_path=args.config, encrypted=args.encrypted)
    elif args.command == 'update-keys':
        success = run_update_keys(config, config_path=args.config, encrypted=args.encrypted)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
