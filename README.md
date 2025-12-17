# Snowflake Key Pair Rotation Tool

Automates Snowflake key-pair authentication setup and rotation with Hevo Data destinations.

## Features

- Generate RSA 2048-bit key pairs (encrypted or non-encrypted)
- Configure Snowflake users with RSA public keys
- Create/update Hevo Data destinations with key-pair authentication
- Seamless key rotation with automatic backup

## Installation

```bash
cd sf_rotation
pip install -r requirements.txt
```

## Configuration

1. Copy the example config:
```bash
cp config/config.yaml.example config/config.yaml
```

2. Edit `config/config.yaml` with your credentials:
- Snowflake account URL, admin credentials, target user
- Hevo API credentials and destination details
- Key encryption preferences

## Usage

### Initial Setup

Sets up key-pair authentication for the first time:

```bash
python main.py setup --config config/config.yaml
```

With encrypted private key:
```bash
python main.py setup --config config/config.yaml --encrypted
```

### Key Rotation

Rotates existing keys (requires `destination_id` in config):

```bash
python main.py rotate --config config/config.yaml
```

## Process Flow

### Setup Mode
1. Generate RSA key pair
2. Connect to Snowflake (username/password)
3. Set `RSA_PUBLIC_KEY` for target user
4. Create Hevo destination with private key
5. Save destination ID

### Rotate Mode
1. Backup existing keys
2. Generate new key pair
3. Set `RSA_PUBLIC_KEY_2` in Snowflake
4. Update Hevo destination with new private key
5. Unset old `RSA_PUBLIC_KEY`

## Project Structure

```
sf_rotation/
├── config/
│   └── config.yaml.example
├── src/
│   ├── key_generator.py      # OpenSSL key generation
│   ├── snowflake_client.py   # Snowflake connection/key management
│   ├── hevo_client.py        # Hevo API client
│   └── utils.py              # Helper functions
├── keys/                     # Generated keys (gitignored)
├── main.py                   # Main entry point
├── requirements.txt
└── README.md
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
