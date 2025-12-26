"""HTTP proxy server for caching LLM API requests."""

import json
from typing import Optional
from pathlib import Path

try:
    from flask import Flask, request, jsonify, Response
    import requests
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from .cache import Cache
from .hasher import hash_request


class CacheProxy:
    """
    HTTP proxy that caches LLM API responses.

    Sits between your application and the LLM API, caching responses
    for identical requests.
    """

    # Known API endpoints and their chat completion paths
    ENDPOINTS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "chat_path": "/chat/completions",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "chat_path": "/messages",
        },
    }

    def __init__(
        self,
        cache: Optional[Cache] = None,
        target_url: Optional[str] = None,
        provider: str = "openai",
    ):
        """
        Initialize the proxy.

        Args:
            cache: Cache instance. Creates default if None.
            target_url: Target API URL. Uses provider default if None.
            provider: API provider (openai, anthropic)
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask and requests required. Install with: pip install flask requests")

        self.cache = cache or Cache()
        self.provider = provider

        if target_url:
            self.target_url = target_url.rstrip("/")
        else:
            self.target_url = self.ENDPOINTS.get(provider, {}).get(
                "base_url", "https://api.openai.com/v1"
            )

        self.app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route("/v1/chat/completions", methods=["POST"])
        def chat_completions():
            return self._handle_chat_completion()

        @self.app.route("/v1/messages", methods=["POST"])
        def anthropic_messages():
            return self._handle_chat_completion()

        @self.app.route("/cache/stats", methods=["GET"])
        def cache_stats():
            return jsonify(self.cache.stats())

        @self.app.route("/cache/clear", methods=["POST"])
        def cache_clear():
            self.cache.clear()
            return jsonify({"status": "cleared"})

        @self.app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok"})

    def _handle_chat_completion(self) -> Response:
        """Handle a chat completion request."""
        data = request.get_json()

        # Extract cacheable parameters
        messages = data.get("messages", [])
        model = data.get("model", "unknown")
        temperature = data.get("temperature")
        max_tokens = data.get("max_tokens")
        tools = data.get("tools")

        # Don't cache streaming requests
        if data.get("stream", False):
            return self._forward_request(data)

        # Generate cache key
        cache_key = hash_request(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            # Add header to indicate cache hit
            response = jsonify(cached)
            response.headers["X-Cache"] = "HIT"
            return response

        # Forward to actual API
        result = self._forward_request(data)

        if result.status_code == 200:
            # Cache successful response
            response_data = result.get_json()
            self.cache.set(cache_key, response_data, model)

            response = jsonify(response_data)
            response.headers["X-Cache"] = "MISS"
            return response

        return result

    def _forward_request(self, data: dict) -> Response:
        """Forward request to the actual API."""
        # Determine target path
        if self.provider == "anthropic":
            path = "/messages"
        else:
            path = "/chat/completions"

        url = f"{self.target_url}{path}"

        # Forward headers (especially auth)
        headers = {}
        for key in ["Authorization", "X-Api-Key", "Anthropic-Version", "Content-Type"]:
            if key in request.headers:
                headers[key] = request.headers[key]

        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        try:
            resp = requests.post(url, json=data, headers=headers, timeout=120)
            return Response(
                resp.content,
                status=resp.status_code,
                headers={"Content-Type": "application/json"}
            )
        except requests.RequestException as e:
            return jsonify({"error": str(e)}), 502

    def run(self, host: str = "127.0.0.1", port: int = 8080, debug: bool = False):
        """Run the proxy server."""
        self.app.run(host=host, port=port, debug=debug)


def create_app(
    cache_path: Optional[Path] = None,
    ttl_seconds: Optional[int] = None,
    target_url: Optional[str] = None,
    provider: str = "openai",
) -> Flask:
    """
    Create a Flask app for the cache proxy.

    Useful for running with gunicorn or other WSGI servers.
    """
    cache = Cache(path=cache_path, ttl_seconds=ttl_seconds)
    proxy = CacheProxy(cache=cache, target_url=target_url, provider=provider)
    return proxy.app
