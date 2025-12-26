"""LLM Cache - Local caching layer for LLM API responses."""

__version__ = "0.1.0"

from .cache import Cache
from .hasher import hash_request

__all__ = ["Cache", "hash_request"]
