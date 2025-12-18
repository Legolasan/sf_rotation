"""
Snowflake Key Pair Rotation Tool

A Python package for automating Snowflake key-pair authentication
setup and rotation with Hevo Data destinations.
"""

__version__ = "1.2.5"

from .key_generator import KeyGenerator, KeyGenerationError
from .snowflake_client import SnowflakeClient, SnowflakeClientError
from .hevo_client import HevoClient, HevoClientError

__all__ = [
    '__version__',
    'KeyGenerator',
    'KeyGenerationError',
    'SnowflakeClient',
    'SnowflakeClientError',
    'HevoClient',
    'HevoClientError',
]
