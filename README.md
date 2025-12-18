# Snowflake Key Pair Rotation Tool

[![PyPI version](https://badge.fury.io/py/sf-rotation.svg)](https://badge.fury.io/py/sf-rotation)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automates Snowflake key-pair authentication setup and rotation with Hevo Data destinations.

## Installation

### From PyPI (Recommended)

```bash
pip install sf-rotation
```

### From GitHub

```bash
pip install git+https://github.com/Legolasan/sf_rotation.git
```

### From Source

```bash
git clone https://github.com/Legolasan/sf_rotation.git
cd sf_rotation
pip install .
```

### Development Mode

```bash
git clone https://github.com/Legolasan/sf_rotation.git
cd sf_rotation
pip install -e .
```

## Configuration

1. Create a config file based on the example:
```bash
mkdir -p config
curl -o config/config.yaml https://raw.githubusercontent.com/Legolasan/sf_rotation/main/config/config.yaml.example
```

2. Edit `config/config.yaml` with your credentials:
- Snowflake account URL, admin credentials, target user
- Hevo API credentials and destination details
- Key encryption preferences

## Usage

### Command Line Interface

After installation, the `sf-rotation` command is available:

```bash
# Initial setup (creates new Hevo destination, saves destination_id to config)
sf-rotation setup --config config/config.yaml

# Update keys for existing destination (requires destination_id in config)
sf-rotation update-keys --config config/config.yaml

# Key rotation (for ongoing key rotations)
sf-rotation rotate --config config/config.yaml

# With encrypted private key
sf-rotation setup --config config/config.yaml --encrypted
```

### Commands Overview

| Command | Description | Creates Hevo Destination? |
|---------|-------------|---------------------------|
| `setup` | Initial setup - creates new Hevo destination | Yes |
| `update-keys` | Update keys for existing Hevo destination | No (requires `destination_id`) |
| `rotate` | Rotate keys with zero-downtime | No (requires `destination_id`) |

### As Python Module

```bash
python -m sf_rotation setup --config config/config.yaml
python -m sf_rotation rotate --config config/config.yaml
```

### Programmatic Usage

```python
from sf_rotation import KeyGenerator, SnowflakeClient, HevoClient

# Generate keys (returns: private_key_path, public_key_path, backup_path)
generator = KeyGenerator(output_directory="./keys")
private_key_path, public_key_path, backup_path = generator.generate_key_pair(
    key_name="rsa_key",
    encrypted=False
)

# Connect to Snowflake
sf_client = SnowflakeClient(
    account_url="your_account.snowflakecomputing.com",
    username="admin",
    password="password"
)

# Set public key for user
public_key = generator.read_public_key(public_key_path)
formatted_key = generator.format_public_key_for_snowflake(public_key)
sf_client.set_rsa_public_key("target_user", formatted_key)

# Create Hevo destination
hevo = HevoClient(
    base_url="https://us.hevodata.com",
    username="hevo_user",
    password="hevo_pass"
)
private_key = generator.read_private_key(private_key_path)
hevo.create_destination(
    name="my_snowflake",
    account_url="your_account.snowflakecomputing.com",
    warehouse="WAREHOUSE",
    database_name="DATABASE",
    database_user="target_user",
    private_key=private_key
)
```

## Features

- Generate RSA 2048-bit key pairs (encrypted or non-encrypted)
- Configure Snowflake users with RSA public keys
- Create/update Hevo Data destinations with key-pair authentication
- Seamless key rotation with automatic backup
- CLI and programmatic interfaces

## Process Flow

### Setup Mode (New Destination)
1. Generate RSA key pair
2. Connect to Snowflake (username/password)
3. Set `RSA_PUBLIC_KEY` for target user
4. Create Hevo destination with private key
5. Auto-save `destination_id` to config file

### Update-Keys Mode (Existing Destination)
1. Verify `destination_id` exists in config
2. Generate RSA key pair
3. Connect to Snowflake and set public key
4. Update existing Hevo destination with private key

### Rotate Mode (Key Rotation)
1. Backup existing keys
2. Generate new key pair
3. Set `RSA_PUBLIC_KEY_2` in Snowflake
4. Update Hevo destination with new private key
5. Unset old `RSA_PUBLIC_KEY`

## Project Structure

```
sf_rotation/
├── src/sf_rotation/
│   ├── __init__.py           # Package exports
│   ├── main.py               # CLI entry point
│   ├── key_generator.py      # OpenSSL key generation
│   ├── snowflake_client.py   # Snowflake connection/key management
│   ├── hevo_client.py        # Hevo API client
│   └── utils.py              # Helper functions
├── config/
│   └── config.yaml.example   # Configuration template
├── pyproject.toml            # Package configuration
├── README.md
└── WORKFLOW.md               # Detailed workflow documentation
```

## Requirements

- Python 3.8+
- OpenSSL (for key generation)
- Snowflake account with admin access
- Hevo Data account with API access

## Security Notes

- Private keys are stored with 600 permissions
- Keys directory is gitignored
- Config files with credentials are gitignored
- Passphrase prompted at runtime (not stored in config)

## License

MIT License - see LICENSE file for details.
