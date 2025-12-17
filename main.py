#!/usr/bin/env python3
"""
Snowflake Key Pair Rotation Tool

Main orchestrator script for setting up and rotating Snowflake key-pair
authentication with Hevo Data destinations.

Usage:
    python main.py setup --config config/config.yaml
    python main.py rotate --config config/config.yaml
    python main.py setup --config config/config.yaml --encrypted
"""

import argparse
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.key_generator import KeyGenerator, KeyGenerationError
from src.snowflake_client import SnowflakeClient, SnowflakeClientError
from src.hevo_client import HevoClient, HevoClientError
from src.utils import (
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


def run_setup(config: dict, encrypted: bool = False) -> bool:
    """
    Run the initial key pair setup process.
    
    Steps:
    1. Generate key pair
    2. Connect to Snowflake
    3. Set RSA_PUBLIC_KEY for user
    4. Create Hevo destination with private key
    5. Save destination_id to config
    
    Args:
        config: Configuration dictionary
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
        # Step 1: Generate key pair
        print_step(1, "Generating RSA key pair")
        
        key_generator = KeyGenerator(output_directory=keys_dir)
        private_key_path, public_key_path = key_generator.generate_key_pair(
            key_name="rsa_key",
            encrypted=encrypted,
            passphrase=passphrase
        )
        
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
        
        # Step 3: Set RSA_PUBLIC_KEY for user
        print_step(3, f"Setting RSA_PUBLIC_KEY for user: {sf_config['user_to_modify']}")
        
        sf_client.set_rsa_public_key(
            user=sf_config['user_to_modify'],
            public_key=formatted_public_key
        )
        
        # Verify key was set
        sf_client.verify_key_setup(sf_config['user_to_modify'])
        print_success("RSA_PUBLIC_KEY set successfully in Snowflake")
        
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
            
            # Step 5: Save destination_id to config
            print_step(5, "Saving destination ID to configuration")
            config['hevo']['destination_id'] = str(destination_id)
            print_info("Remember to save this destination_id in your config file for future rotations")
        
        print_success("Hevo destination created successfully")
        
        print("\n" + "="*60)
        print("SETUP COMPLETE!")
        print("="*60)
        print(f"\nKey files location: {keys_dir}/")
        print(f"  - Private key: rsa_key.p8")
        print(f"  - Public key: rsa_key.pub")
        if destination_id:
            print(f"\nHevo Destination ID: {destination_id}")
            print("(Save this ID in your config.yaml for future key rotations)")
        
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


def run_rotate(config: dict, encrypted: bool = False) -> bool:
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
        private_key_path, public_key_path = key_generator.generate_key_pair(
            key_name="new_rsa_key",
            encrypted=encrypted,
            passphrase=passphrase
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
        
        # Step 4: Set RSA_PUBLIC_KEY_2 with new key
        print_step(4, f"Setting RSA_PUBLIC_KEY_2 for user: {sf_config['user_to_modify']}")
        
        sf_client.set_rsa_public_key_2(
            user=sf_config['user_to_modify'],
            public_key=formatted_public_key
        )
        
        print_success("RSA_PUBLIC_KEY_2 set successfully (new key active)")
        
        # Step 5: Update Hevo destination with new private key
        print_step(5, f"Updating Hevo destination (ID: {destination_id}) with new private key")
        
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
        
        # Step 6: Unset old RSA_PUBLIC_KEY
        print_step(6, f"Unsetting old RSA_PUBLIC_KEY for user: {sf_config['user_to_modify']}")
        
        if confirm_action("Confirm: Unset the old RSA_PUBLIC_KEY? (This completes the rotation)"):
            sf_client.unset_rsa_public_key(sf_config['user_to_modify'])
            print_success("Old RSA_PUBLIC_KEY unset successfully")
        else:
            print_warning("Skipped unsetting old key. You may need to do this manually later.")
            print_info("Command: ALTER USER <user> UNSET RSA_PUBLIC_KEY;")
        
        # Verify final state
        print_info("Verifying final key configuration...")
        sf_client.verify_key_setup(sf_config['user_to_modify'])
        
        # Rename new keys to standard names
        print_step(7, "Finalizing key files")
        
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Snowflake Key Pair Rotation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Initial setup:
    python main.py setup --config config/config.yaml

  Key rotation:
    python main.py rotate --config config/config.yaml

  With encrypted keys:
    python main.py setup --config config/config.yaml --encrypted
    python main.py rotate --config config/config.yaml --encrypted
        """
    )
    
    parser.add_argument(
        'command',
        choices=['setup', 'rotate'],
        help="Command to execute: 'setup' for initial configuration, 'rotate' for key rotation"
    )
    
    parser.add_argument(
        '--config', '-c',
        required=True,
        help="Path to configuration YAML file"
    )
    
    parser.add_argument(
        '--encrypted', '-e',
        action='store_true',
        help="Use encrypted private key (passphrase will be prompted)"
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help="Logging level (default: INFO)"
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
        success = run_setup(config, encrypted=args.encrypted)
    elif args.command == 'rotate':
        success = run_rotate(config, encrypted=args.encrypted)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
