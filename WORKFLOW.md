# Snowflake Key Pair Rotation - Workflow Guide

This document explains how the Snowflake Key Pair Rotation tool works step by step.

## Overview

The tool has two modes: **Setup** (initial configuration) and **Rotate** (key rotation).

---

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install sf-rotation
```

### Option 2: Install from GitHub

```bash
pip install git+https://github.com/Legolasan/sf_rotation.git
```

### Option 3: Install from Source

```bash
git clone https://github.com/Legolasan/sf_rotation.git
cd sf_rotation
pip install .
```

---

## Quick Start

### Step 1: Install the Package

```bash
pip install sf-rotation
```

### Step 2: Create Configuration File

```bash
mkdir -p config
curl -o config/config.yaml https://raw.githubusercontent.com/Legolasan/sf_rotation/main/config/config.yaml.example
```

Or manually create `config/config.yaml`:

```yaml
snowflake:
  account_url: "your_account.snowflakecomputing.com"
  username: "admin_username"
  password: "admin_password"
  warehouse: "your_warehouse"
  database: "your_database"
  user_to_modify: "hevo_service_user"

hevo:
  base_url: "https://us.hevodata.com"
  username: "your_hevo_username"
  password: "your_hevo_password"
  destination_id: ""
  destination_name: "snowflake_destination"

keys:
  encrypted: false
  passphrase: ""
  output_directory: "./keys"
```

### Step 3: Run Initial Setup

```bash
sf-rotation setup --config config/config.yaml
```

### Step 4: Run Key Rotation (when needed)

```bash
sf-rotation rotate --config config/config.yaml
```

---

## Setup Mode (`sf-rotation setup`)

This is for first-time key pair configuration:

### Step 1: Generate RSA Key Pair
- Runs OpenSSL commands via subprocess:
  - **Non-encrypted**: `openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt`
  - **Encrypted**: `openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 des3 -inform PEM -out rsa_key.p8`
- Generates public key: `openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub`
- Saves keys to `./keys/` directory

### Step 2: Connect to Snowflake
- Uses `snowflake-connector-python` with username/password authentication
- This is the admin account that has permission to alter other users

### Step 3: Set RSA_PUBLIC_KEY in Snowflake
- Formats the public key (removes PEM headers, joins into single line)
- Executes: `ALTER USER <target_user> SET RSA_PUBLIC_KEY='<formatted_key>'`

### Step 4: Create Hevo Destination
- Calls Hevo API: `POST /api/v1/destinations`
- Sends the private key content with `authentication_type: "PRIVATE_KEY"`
- Uses Basic Auth (username/password)

### Step 5: Save Destination ID
- Extracts `destination_id` from API response
- User saves this ID in config for future rotations

---

## Rotate Mode (`sf-rotation rotate`)

This is for rotating existing keys:

### Step 1: Backup Existing Keys
- Copies current keys from `./keys/` to `./keys/backups/<timestamp>/`

### Step 2: Generate New Key Pair
- Same as setup, but saves as `new_rsa_key.p8` and `new_rsa_key.pub`

### Step 3: Connect to Snowflake
- Same admin connection as setup

### Step 4: Set RSA_PUBLIC_KEY_2 (New Key)
- Executes: `ALTER USER <target_user> SET RSA_PUBLIC_KEY_2='<new_key>'`
- **Both keys are now active** - Snowflake accepts either

### Step 5: Update Hevo Destination
- Calls Hevo API: `PATCH /api/v1/destinations/<destination_id>`
- Updates with new private key
- Hevo now uses the new key to authenticate

### Step 6: Unset Old RSA_PUBLIC_KEY
- Prompts for confirmation
- Executes: `ALTER USER <target_user> UNSET RSA_PUBLIC_KEY`
- Old key is now invalid

### Step 7: Finalize
- Renames `new_rsa_key.p8` to `rsa_key.p8`
- Renames `new_rsa_key.pub` to `rsa_key.pub`

---

## CLI Reference

### Available Commands

| Command | Description |
|---------|-------------|
| `sf-rotation setup --config <path>` | Initial key pair setup |
| `sf-rotation rotate --config <path>` | Rotate existing keys |

### Options

| Option | Description |
|--------|-------------|
| `--config`, `-c` | Path to YAML configuration file (required) |
| `--encrypted`, `-e` | Use encrypted private key (passphrase prompted) |
| `--log-level` | Logging level: DEBUG, INFO, WARNING, ERROR |

### Examples

```bash
# Initial setup with non-encrypted key
sf-rotation setup --config config/config.yaml

# Initial setup with encrypted key
sf-rotation setup --config config/config.yaml --encrypted

# Key rotation
sf-rotation rotate --config config/config.yaml

# With debug logging
sf-rotation setup --config config/config.yaml --log-level DEBUG
```

### Alternative: Run as Python Module

```bash
python -m sf_rotation setup --config config/config.yaml
python -m sf_rotation rotate --config config/config.yaml
```

---

## Visual Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        SETUP MODE                               │
├─────────────────────────────────────────────────────────────────┤
│  [OpenSSL] ──► Private Key + Public Key                         │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── ALTER USER SET RSA_PUBLIC_KEY                  │
│       │                                                         │
│       ▼                                                         │
│  [Hevo API] ◄── POST /destinations (with private key)           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       ROTATE MODE                               │
├─────────────────────────────────────────────────────────────────┤
│  [Backup] ──► Old keys saved to backups/                        │
│       │                                                         │
│       ▼                                                         │
│  [OpenSSL] ──► New Private Key + Public Key                     │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── ALTER USER SET RSA_PUBLIC_KEY_2 (new)          │
│       │         (both keys now valid)                           │
│       ▼                                                         │
│  [Hevo API] ◄── PATCH /destinations (new private key)           │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── ALTER USER UNSET RSA_PUBLIC_KEY (old)          │
│                  (only new key valid now)                       │
└─────────────────────────────────────────────────────────────────┘
```

## Key Insight

During rotation, **both keys are temporarily valid** (RSA_PUBLIC_KEY and RSA_PUBLIC_KEY_2), which ensures zero downtime while Hevo switches to the new key.

---

## Module Reference

| Module | Purpose |
|--------|---------|
| `sf_rotation.key_generator` | OpenSSL key generation |
| `sf_rotation.snowflake_client` | Snowflake connection & ALTER USER commands |
| `sf_rotation.hevo_client` | Hevo REST API client |
| `sf_rotation.utils` | Logging, config, helpers |
| `sf_rotation.main` | CLI orchestrator (setup/rotate commands) |

---

## Programmatic Usage

You can also use the package programmatically in your Python code:

```python
from sf_rotation import KeyGenerator, SnowflakeClient, HevoClient

# Generate keys
generator = KeyGenerator(output_directory="./keys")
private_key_path, public_key_path = generator.generate_key_pair(
    key_name="rsa_key",
    encrypted=False
)

# Read keys
private_key = generator.read_private_key(private_key_path)
public_key = generator.read_public_key(public_key_path)
formatted_public_key = generator.format_public_key_for_snowflake(public_key)

# Configure Snowflake user
sf_client = SnowflakeClient(
    account_url="account.snowflakecomputing.com",
    username="admin",
    password="password"
)
sf_client.set_rsa_public_key("target_user", formatted_public_key)

# Create Hevo destination
hevo = HevoClient(
    base_url="https://us.hevodata.com",
    username="hevo_user",
    password="hevo_pass"
)
hevo.create_destination(
    name="my_snowflake_dest",
    account_url="account.snowflakecomputing.com",
    warehouse="WAREHOUSE",
    database_name="DATABASE",
    database_user="target_user",
    private_key=private_key
)
```
