# Snowflake Key Pair Rotation - Workflow Guide

This document explains how the Snowflake Key Pair Rotation tool works step by step.

## Overview

The tool has two modes: **Setup** (initial configuration) and **Rotate** (key rotation).

---

## Setup Mode (`python main.py setup`)

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

## Rotate Mode (`python main.py rotate`)

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
| `src/key_generator.py` | OpenSSL key generation |
| `src/snowflake_client.py` | Snowflake connection & ALTER USER commands |
| `src/hevo_client.py` | Hevo REST API client |
| `src/utils.py` | Logging, config, helpers |
| `main.py` | Orchestrator (setup/rotate commands) |
