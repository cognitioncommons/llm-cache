# llm-cache

Local caching layer for LLM API responses. Save money and speed up development.

## Installation

```bash
pip install llm-cache
```

For proxy server mode:

```bash
pip install llm-cache[server]
```

## Usage

### Proxy Server Mode

Start a caching proxy that sits between your app and the LLM API:

```bash
# Start proxy for OpenAI
llm-cache serve --port 8080

# Start proxy for Anthropic
llm-cache serve --port 8080 --provider anthropic

# With TTL (cache expires after 1 hour)
llm-cache serve --port 8080 --ttl 3600
```

Then configure your client:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="your-api-key"  # Still sent to real API
)

# Requests are automatically cached
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Cache Management

```bash
# View statistics
llm-cache stats

# Clear all cache
llm-cache clear

# Clear entries older than 7 days
llm-cache clear --older-than 7

# Export cache for sharing
llm-cache export backup.db

# Import cache
llm-cache import backup.db
```

### Python API

```python
from llm_cache import Cache, hash_request

# Create cache
cache = Cache(ttl_seconds=3600, max_entries=10000)

# Generate cache key
key = hash_request(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4",
    temperature=0.7
)

# Check cache
cached = cache.get(key)
if cached:
    print("Cache hit!")
    response = cached
else:
    # Make API call
    response = call_llm_api(...)
    cache.set(key, response, model="gpt-4")

# Get stats
stats = cache.stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")
```

## How It Works

1. **Request Hashing**: Each request is hashed based on messages, model, temperature, and other parameters
2. **SQLite Storage**: Responses are stored in a local SQLite database
3. **TTL Support**: Entries can expire after a configurable time
4. **LRU Eviction**: When max entries is reached, least recently used entries are evicted

## Features

- Content-addressable storage (identical requests → same cache key)
- SQLite backend (portable, no server needed)
- TTL support (time-based expiration)
- Size limits with LRU eviction
- Proxy mode (drop-in replacement for API endpoints)
- Cache hit/miss statistics
- Export/import for sharing cached responses
- Supports OpenAI and Anthropic APIs

## Cache Headers

When using proxy mode, responses include cache status headers:

- `X-Cache: HIT` - Response served from cache
- `X-Cache: MISS` - Response fetched from API and cached

## Configuration

### Environment Variables

- `LLM_CACHE_PATH`: Path to cache database (default: `~/.llm-cache/cache.db`)
- `LLM_CACHE_TTL`: Default TTL in seconds

### Cache Location

Default: `~/.llm-cache/cache.db`

Override with `--cache-path` option or `LLM_CACHE_PATH` environment variable.

## Limitations

- Streaming responses are not cached (passed through directly)
- Non-deterministic requests (temperature > 0) will cache first response

## License

MIT License - see [LICENSE](LICENSE) for details.

Part of the [Cognition Commons](https://cognitioncommons.org) project.
