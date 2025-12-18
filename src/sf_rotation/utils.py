"""
Utilities Module

Helper functions for logging, configuration management, and file operations.
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from getpass import getpass


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("sf_rotation")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Save configuration to YAML file.
    
    Args:
        config: Configuration dictionary
        config_path: Path to save the configuration
    """
    config_path = Path(config_path)
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_passphrase(prompt: str = "Enter passphrase: ") -> str:
    """
    Securely prompt for a passphrase.
    
    Args:
        prompt: Prompt message to display
        
    Returns:
        Entered passphrase
    """
    return getpass(prompt)


def backup_keys(
    keys_directory: str,
    backup_directory: Optional[str] = None
) -> Optional[str]:
    """
    Backup existing keys before rotation.
    
    Args:
        keys_directory: Directory containing current keys
        backup_directory: Optional custom backup location
        
    Returns:
        Path to backup directory, or None if no keys to backup
    """
    keys_dir = Path(keys_directory)
    
    if not keys_dir.exists():
        return None
    
    # Find existing key files
    key_files = list(keys_dir.glob("*.p8")) + list(keys_dir.glob("*.pub"))
    
    if not key_files:
        return None
    
    # Create backup directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if backup_directory:
        backup_dir = Path(backup_directory)
    else:
        backup_dir = keys_dir / "backups" / timestamp
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy key files to backup
    import shutil
    for key_file in key_files:
        shutil.copy2(key_file, backup_dir / key_file.name)
    
    return str(backup_dir)


def validate_config(config: Dict[str, Any]) -> tuple[bool, list]:
    """
    Validate configuration structure and required fields.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Required sections
    required_sections = ['snowflake', 'hevo', 'keys']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: {section}")
    
    if errors:
        return False, errors
    
    # Snowflake required fields
    sf_required = ['account_url', 'username', 'password', 'user_to_modify']
    for field in sf_required:
        if not config['snowflake'].get(field):
            errors.append(f"Missing required Snowflake field: {field}")
    
    # Hevo required fields
    hevo_required = ['base_url', 'username', 'password', 'destination_name']
    for field in hevo_required:
        if not config['hevo'].get(field):
            errors.append(f"Missing required Hevo field: {field}")
    
    # Keys configuration
    if config['keys'].get('encrypted') and not config['keys'].get('passphrase'):
        # Passphrase can be prompted at runtime, so this is just a warning
        pass
    
    return len(errors) == 0, errors


def print_banner():
    """Print application banner."""
    banner = """
╔════════════════════════════════════════════════════════════╗
║           Snowflake Key Pair Rotation Tool                 ║
║                                                            ║
║  Automates key pair setup and rotation for Snowflake       ║
║  authentication with Hevo Data destinations.               ║
╚════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_step(step_number: int, description: str):
    """
    Print a formatted step message.
    
    Args:
        step_number: Step number in the process
        description: Description of the step
    """
    print(f"\n{'='*60}")
    print(f"Step {step_number}: {description}")
    print('='*60)


def print_success(message: str):
    """Print a success message."""
    print(f"\n✅ SUCCESS: {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"\n❌ ERROR: {message}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"\n⚠️  WARNING: {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"\nℹ️  INFO: {message}")


def confirm_action(prompt: str) -> bool:
    """
    Ask for user confirmation.
    
    Args:
        prompt: Confirmation prompt
        
    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input(f"\n{prompt} (yes/no): ").lower().strip()
        if response in ('yes', 'y'):
            return True
        elif response in ('no', 'n'):
            return False
        print("Please enter 'yes' or 'no'")


def format_key_for_display(key_content: str, max_length: int = 50) -> str:
    """
    Format a key for safe display (truncated).
    
    Args:
        key_content: Full key content
        max_length: Maximum characters to display
        
    Returns:
        Truncated key string
    """
    # Remove headers and get just the key body
    lines = key_content.strip().split('\n')
    key_body = ''.join([l for l in lines if not l.startswith('-----')])
    
    if len(key_body) > max_length:
        return f"{key_body[:max_length]}..."
    return key_body


if __name__ == "__main__":
    # Test utilities
    print_banner()
    print_step(1, "Testing utilities module")
    print_success("Utilities module loaded successfully")
