# Snowflake Key Pair Rotation - Workflow Guide

This document explains how the Snowflake Key Pair Rotation tool works step by step.

## Overview

The tool has three modes:
- **Setup** - Initial configuration with new Hevo destination
- **Update-Keys** - Update keys for existing Hevo destination  
- **Rotate** - Zero-downtime key rotation (can run multiple times)

---

## Installation

```bash
pip install sf-rotation
```

**Alternative installation methods:**
```bash
# From GitHub
pip install git+https://github.com/Legolasan/sf_rotation.git

# From source
git clone https://github.com/Legolasan/sf_rotation.git && cd sf_rotation && pip install .
```

---

# Step-by-Step Guides

## Scenario 1: Setup - New Hevo Destination

Use this when you want to **create a new Hevo destination** with key-pair authentication.

### Step 1: Install the tool

```bash
pip install sf-rotation
```

### Step 2: Create a directory for your project

```bash
mkdir my-snowflake-rotation
cd my-snowflake-rotation
```

### Step 3: Create configuration file

```bash
mkdir -p config
```

Create `config/config.yaml` with your credentials:

```yaml
snowflake:
  account_url: "your_account.snowflakecomputing.com"
  username: "admin_username"          # Admin user with ALTER USER permission
  password: "admin_password"
  warehouse: "your_warehouse"
  database: "your_database"
  user_to_modify: "hevo_service_user" # The user Hevo will use to connect

hevo:
  base_url: "https://us.hevodata.com" # or your Hevo region URL
  username: "your_hevo_username"
  password: "your_hevo_password"
  destination_id: ""                  # Leave empty for setup
  destination_name: "snowflake_destination"

keys:
  encrypted: false                    # Set true for encrypted private key
  passphrase: ""                      # Leave empty to be prompted
  output_directory: "./keys"
```

### Step 4: Run setup

```bash
sf-rotation setup --config config/config.yaml
```

**For encrypted private key:**
```bash
sf-rotation setup --config config/config.yaml --encrypted
```

### What happens:
1. ✅ Generates RSA key pair → saves to `./keys/rsa_key.p8` and `./keys/rsa_key.pub`
2. ✅ Connects to Snowflake with admin credentials
3. ✅ Sets `RSA_PUBLIC_KEY` for `user_to_modify`
4. ✅ Creates Hevo destination via API
5. ✅ **Auto-saves `destination_id` to config file** (for future rotations)

---

## Scenario 2: Update-Keys - Existing Hevo Destination

Use this when you **already have a Hevo destination** (created via UI or API) and want to configure key-pair authentication.

### Step 1: Install the tool

```bash
pip install sf-rotation
```

### Step 2: Create a directory for your project

```bash
mkdir my-snowflake-rotation
cd my-snowflake-rotation
```

### Step 3: Get your Hevo destination ID

Find your destination ID from:
- Hevo Dashboard → Destinations → Your Destination → URL contains the ID
- Or use Hevo API: `GET /api/v1/destinations`

### Step 4: Create configuration file

```bash
mkdir -p config
```

Create `config/config.yaml` with your credentials:

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
  destination_id: "123456"             # ⬅️ YOUR EXISTING DESTINATION ID
  destination_name: "snowflake_destination"

keys:
  encrypted: false
  passphrase: ""
  output_directory: "./keys"
```

### Step 5: Run update-keys

```bash
sf-rotation update-keys --config config/config.yaml
```

**For encrypted private key:**
```bash
sf-rotation update-keys --config config/config.yaml --encrypted
```

### What happens:
1. ✅ Verifies `destination_id` exists in config
2. ✅ Generates RSA key pair → saves to `./keys/`
3. ✅ Connects to Snowflake with admin credentials
4. ✅ Sets `RSA_PUBLIC_KEY` (or `RSA_PUBLIC_KEY_2` if slot 1 is occupied)
5. ✅ **Updates existing Hevo destination** (does NOT create new)

---

## Scenario 3: Rotate - Key Rotation (Repeatable)

Use this for **ongoing key rotations**. Can be run **multiple times** without conflicts.

### Prerequisites
- You've already run `setup` or `update-keys` successfully
- `destination_id` is set in your config file

### Step 1: Run rotation

```bash
sf-rotation rotate --config config/config.yaml
```

**For encrypted private key:**
```bash
sf-rotation rotate --config config/config.yaml --encrypted
```

### What happens:
1. ✅ Backs up current keys to `./keys/backups/<timestamp>/`
2. ✅ Generates new RSA key pair
3. ✅ Connects to Snowflake
4. ✅ **Detects current key slot** (RSA_PUBLIC_KEY or RSA_PUBLIC_KEY_2)
5. ✅ **Sets new key in the OTHER slot** (zero-downtime - both keys valid)
6. ✅ Updates Hevo destination with new private key
7. ✅ **Unsets the OLD key slot** (after confirmation)
8. ✅ Renames new keys to standard names

### Key Slot Alternation (Multiple Rotations)

The tool automatically alternates between key slots:

| Run | Current Key Slot | New Key Slot | After Rotation |
|-----|-----------------|--------------|----------------|
| Setup | - | Slot 1 | Key A in Slot 1 |
| Rotate 1 | Slot 1 | Slot 2 | Key B in Slot 2 |
| Rotate 2 | Slot 2 | Slot 1 | Key C in Slot 1 |
| Rotate 3 | Slot 1 | Slot 2 | Key D in Slot 2 |
| ...and so on | Alternates | Alternates | ✅ No conflicts |

---

# Quick Reference

## Commands

| Command | When to Use | Creates Destination? |
|---------|-------------|---------------------|
| `sf-rotation setup --config config.yaml` | First time, new Hevo destination | ✅ Yes |
| `sf-rotation update-keys --config config.yaml` | First time, existing Hevo destination | ❌ No |
| `sf-rotation rotate --config config.yaml` | Ongoing key rotation | ❌ No |

## Add `--encrypted` for password-protected keys

```bash
sf-rotation setup --config config.yaml --encrypted
sf-rotation update-keys --config config.yaml --encrypted
sf-rotation rotate --config config.yaml --encrypted
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

This is for rotating existing keys. **Can be run multiple times without conflicts.**

### Step 1: Backup Existing Keys
- Copies current keys from `./keys/` to `./keys/backups/<timestamp>/`

### Step 2: Generate New Key Pair
- Same as setup, but saves as `new_rsa_key.p8` and `new_rsa_key.pub`

### Step 3: Connect to Snowflake
- Same admin connection as setup

### Step 4: Detect Current Key Slot
- Queries Snowflake to check which slot has the active key:
  - `RSA_PUBLIC_KEY_FP` (slot 1)
  - `RSA_PUBLIC_KEY_2_FP` (slot 2)
- Determines the **other slot** for the new key

### Step 5: Set New Key in Alternate Slot
- If current key is in slot 1 → `ALTER USER SET RSA_PUBLIC_KEY_2='<new_key>'`
- If current key is in slot 2 → `ALTER USER SET RSA_PUBLIC_KEY='<new_key>'`
- **Both keys are now active** - Snowflake accepts either (zero-downtime)

### Step 6: Update Hevo Destination
- Calls Hevo API: `PATCH /api/v1/destinations/<destination_id>`
- Updates with new private key
- Hevo now uses the new key to authenticate

### Step 7: Unset Old Key Slot
- Prompts for confirmation
- If old key was in slot 1 → `ALTER USER UNSET RSA_PUBLIC_KEY`
- If old key was in slot 2 → `ALTER USER UNSET RSA_PUBLIC_KEY_2`
- Old key is now invalid

### Step 8: Finalize
- Renames `new_rsa_key.p8` to `rsa_key.p8`
- Renames `new_rsa_key.pub` to `rsa_key.pub`

### Why Alternating Slots?
This ensures rotation can run **indefinitely** without conflicts:
```
Rotate 1: Slot 1 → Slot 2 → Unset Slot 1
Rotate 2: Slot 2 → Slot 1 → Unset Slot 2
Rotate 3: Slot 1 → Slot 2 → Unset Slot 1
...repeats forever
```

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
│            (Zero-Downtime, Repeatable Rotation)                 │
├─────────────────────────────────────────────────────────────────┤
│  [Backup] ──► Old keys saved to backups/                        │
│       │                                                         │
│       ▼                                                         │
│  [OpenSSL] ──► New Private Key + Public Key                     │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ──► Detect current key slot (1 or 2)               │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── SET new key in OTHER slot                      │
│       │         (both keys now valid - zero downtime)           │
│       ▼                                                         │
│  [Hevo API] ◄── PATCH /destinations (new private key)           │
│       │                                                         │
│       ▼                                                         │
│  [Snowflake] ◄── UNSET old key slot                             │
│                  (only new key valid now)                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  ROTATION KEY SLOT FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  After Setup:    [Slot 1: Key A]  [Slot 2: Empty]               │
│                        │                                        │
│  Rotate #1:      [Slot 1: Empty]  [Slot 2: Key B] ←── new       │
│                        │                                        │
│  Rotate #2:      [Slot 1: Key C]  [Slot 2: Empty] ←── new       │
│                        │                                        │
│  Rotate #3:      [Slot 1: Empty]  [Slot 2: Key D] ←── new       │
│                        │                                        │
│                  ...alternates forever...                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Insight

- During rotation, **both keys are temporarily valid** (RSA_PUBLIC_KEY and RSA_PUBLIC_KEY_2), ensuring zero downtime while Hevo switches to the new key.
- The rotation **alternates between slots**, allowing you to run it **unlimited times** without conflicts.

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
