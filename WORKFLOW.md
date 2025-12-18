# Snowflake Key Pair Rotation - Workflow Guide

This document explains how the Snowflake Key Pair Rotation tool works step by step.

## Overview

The tool has three modes:
- **Setup** - Initial configuration with new Hevo destination
- **Update-Keys** - Update keys for existing Hevo destination  
- **Rotate** - Zero-downtime key rotation

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

### Step 3: Choose Your Scenario

**Option A: New Hevo Destination**
```bash
sf-rotation setup --config config/config.yaml
```
This creates a new destination and auto-saves `destination_id` to your config.

**Option B: Existing Hevo Destination**
Add your `destination_id` to config, then:
```bash
sf-rotation update-keys --config config/config.yaml
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

### Step 5: Auto-Save Destination ID
- Extracts `destination_id` from API response
- **Automatically saves** to config file for future rotations

---

## Update-Keys Mode (`sf-rotation update-keys`)

Use this when you **already have a Hevo destination** (created via Hevo UI or API) and want to configure key-pair authentication:

### Prerequisites
- Add `destination_id` to your config file:
```yaml
hevo:
  destination_id: "your_existing_destination_id"
```

### Step 1: Verify Destination ID
- Checks that `destination_id` exists in config
- Displays helpful error if missing

### Step 2: Generate RSA Key Pair
- Same as setup mode
- Backs up existing keys if present

### Step 3: Connect to Snowflake
- Uses admin credentials to connect

### Step 4: Set RSA Public Key
- Checks available key slot (RSA_PUBLIC_KEY or RSA_PUBLIC_KEY_2)
- Sets the public key for the target user

### Step 5: Update Hevo Destination
- Calls Hevo API: `PATCH /api/v1/destinations/<destination_id>`
- Updates with new private key
- Does NOT create a new destination

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

| Command | Description | Creates Destination? |
|---------|-------------|---------------------|
| `sf-rotation setup --config <path>` | Initial setup - new Hevo destination | Yes |
| `sf-rotation update-keys --config <path>` | Update keys - existing destination | No |
| `sf-rotation rotate --config <path>` | Rotate keys - zero downtime | No |

### Options

| Option | Description |
|--------|-------------|
| `--config`, `-c` | Path to YAML configuration file (required) |
| `--encrypted`, `-e` | Use encrypted private key (passphrase prompted) |
| `--log-level` | Logging level: DEBUG, INFO, WARNING, ERROR |

### Examples

```bash
# Initial setup - creates new Hevo destination
sf-rotation setup --config config/config.yaml

# Update keys for existing destination
sf-rotation update-keys --config config/config.yaml

# Key rotation with zero downtime
sf-rotation rotate --config config/config.yaml

# With encrypted key
sf-rotation setup --config config/config.yaml --encrypted

# With debug logging
sf-rotation setup --config config/config.yaml --log-level DEBUG
```

### Alternative: Run as Python Module

```bash
python -m sf_rotation setup --config config/config.yaml
python -m sf_rotation update-keys --config config/config.yaml
python -m sf_rotation rotate --config config/config.yaml
```

---

## Visual Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        SETUP MODE                               │
│                   (New Hevo Destination)                        │
├─────────────────────────────────────────────────────────────────┤
│  [OpenSSL] ──► Private Key + Public Key                         │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── ALTER USER SET RSA_PUBLIC_KEY                  │
│       │                                                         │
│       ▼                                                         │
│  [Hevo API] ◄── POST /destinations (creates new)                │
│       │                                                         │
│       ▼                                                         │
│  [Config] ◄── Auto-save destination_id                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     UPDATE-KEYS MODE                            │
│                 (Existing Hevo Destination)                     │
├─────────────────────────────────────────────────────────────────┤
│  [Config] ──► Verify destination_id exists                      │
│       │                                                         │
│       ▼                                                         │
│  [OpenSSL] ──► Private Key + Public Key                         │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── ALTER USER SET RSA_PUBLIC_KEY                  │
│       │                                                         │
│       ▼                                                         │
│  [Hevo API] ◄── PATCH /destinations (update existing)           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       ROTATE MODE                               │
│                   (Zero-Downtime Rotation)                      │
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

# Generate keys (returns: private_key_path, public_key_path, backup_path)
generator = KeyGenerator(output_directory="./keys")
private_key_path, public_key_path, backup_path = generator.generate_key_pair(
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
