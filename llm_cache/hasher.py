"""Request hashing for cache keys."""

import hashlib
import json
from typing import Any, Dict, List, Optional


def normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize messages for consistent hashing."""
    normalized = []
    for msg in messages:
        norm_msg = {
            "role": msg.get("role", ""),
            "content": msg.get("content", ""),
        }
        if "name" in msg:
            norm_msg["name"] = msg["name"]
        if "tool_calls" in msg:
            norm_msg["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg:
            norm_msg["tool_call_id"] = msg["tool_call_id"]
        normalized.append(norm_msg)
    return normalized


def hash_request(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict]] = None,
    **kwargs
) -> str:
    """
    Generate a deterministic hash for an LLM request.

    Args:
        messages: List of message dicts
        model: Model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens
        tools: Tool definitions
        **kwargs: Additional parameters to include in hash

    Returns:
        SHA-256 hash string
    """
    # Build canonical request representation
    request_data = {
        "messages": normalize_messages(messages),
        "model": model,
    }

    # Only include non-None parameters
    if temperature is not None:
        request_data["temperature"] = temperature
    if max_tokens is not None:
        request_data["max_tokens"] = max_tokens
    if tools:
        request_data["tools"] = tools

    # Include any additional kwargs
    for key, value in sorted(kwargs.items()):
        if value is not None:
            request_data[key] = value

    # Create deterministic JSON string
    json_str = json.dumps(request_data, sort_keys=True, separators=(",", ":"))

    # Return SHA-256 hash
    return hashlib.sha256(json_str.encode()).hexdigest()


def hash_completion_request(
    prompt: str,
    model: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs
) -> str:
    """
    Generate a hash for a completion (non-chat) request.

    Args:
        prompt: The prompt string
        model: Model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens
        **kwargs: Additional parameters

    Returns:
        SHA-256 hash string
    """
    request_data = {
        "prompt": prompt,
        "model": model,
    }

    if temperature is not None:
        request_data["temperature"] = temperature
    if max_tokens is not None:
        request_data["max_tokens"] = max_tokens

    for key, value in sorted(kwargs.items()):
        if value is not None:
            request_data[key] = value

    json_str = json.dumps(request_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()
