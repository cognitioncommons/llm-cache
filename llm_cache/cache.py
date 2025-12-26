"""SQLite-based cache for LLM responses."""

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    """A cached response entry."""
    key: str
    response: Dict[str, Any]
    model: str
    created_at: float
    expires_at: Optional[float]
    hit_count: int


class Cache:
    """
    SQLite-based cache for LLM API responses.

    Features:
    - Content-addressable storage (hash-based keys)
    - TTL support
    - Size limits with LRU eviction
    - Hit/miss statistics
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        ttl_seconds: Optional[int] = None,
        max_entries: Optional[int] = None,
    ):
        """
        Initialize the cache.

        Args:
            path: Path to SQLite database. Defaults to ~/.llm-cache/cache.db
            ttl_seconds: Default TTL for entries. None means no expiration.
            max_entries: Maximum number of entries. None means unlimited.
        """
        if path is None:
            path = Path.home() / ".llm-cache" / "cache.db"

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    hit_count INTEGER DEFAULT 0,
                    last_accessed REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache(last_accessed)
            """)

            # Stats table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    key TEXT PRIMARY KEY,
                    value INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO stats (key, value) VALUES ('hits', 0)
            """)
            conn.execute("""
                INSERT OR IGNORE INTO stats (key, value) VALUES ('misses', 0)
            """)
            conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a cached response by key.

        Args:
            key: Cache key (hash)

        Returns:
            Cached response dict or None if not found/expired
        """
        now = time.time()

        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                SELECT response, expires_at FROM cache
                WHERE key = ?
                """,
                (key,)
            )
            row = cursor.fetchone()

            if row is None:
                # Cache miss
                conn.execute(
                    "UPDATE stats SET value = value + 1 WHERE key = 'misses'"
                )
                conn.commit()
                return None

            response_json, expires_at = row

            # Check expiration
            if expires_at is not None and expires_at < now:
                # Expired, delete and return miss
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.execute(
                    "UPDATE stats SET value = value + 1 WHERE key = 'misses'"
                )
                conn.commit()
                return None

            # Cache hit - update stats
            conn.execute(
                """
                UPDATE cache
                SET hit_count = hit_count + 1, last_accessed = ?
                WHERE key = ?
                """,
                (now, key)
            )
            conn.execute(
                "UPDATE stats SET value = value + 1 WHERE key = 'hits'"
            )
            conn.commit()

            return json.loads(response_json)

    def set(
        self,
        key: str,
        response: Dict[str, Any],
        model: str,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Store a response in the cache.

        Args:
            key: Cache key (hash)
            response: Response dict to cache
            model: Model name
            ttl_seconds: TTL override. Uses default if None.
        """
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = now + ttl if ttl is not None else None

        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache
                (key, response, model, created_at, expires_at, hit_count, last_accessed)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (key, json.dumps(response), model, now, expires_at, now)
            )
            conn.commit()

        # Enforce max entries if set
        if self.max_entries:
            self._evict_lru()

    def _evict_lru(self):
        """Evict least recently used entries if over limit."""
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache")
            count = cursor.fetchone()[0]

            if count > self.max_entries:
                # Delete oldest entries
                to_delete = count - self.max_entries
                conn.execute(
                    """
                    DELETE FROM cache WHERE key IN (
                        SELECT key FROM cache
                        ORDER BY last_accessed ASC
                        LIMIT ?
                    )
                    """,
                    (to_delete,)
                )
                conn.commit()

    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.

        Args:
            key: Cache key

        Returns:
            True if entry was deleted, False if not found
        """
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def clear(self, older_than_days: Optional[int] = None):
        """
        Clear the cache.

        Args:
            older_than_days: Only clear entries older than this. None clears all.
        """
        with sqlite3.connect(self.path) as conn:
            if older_than_days is not None:
                cutoff = time.time() - (older_than_days * 86400)
                conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
            else:
                conn.execute("DELETE FROM cache")

            # Reset stats
            conn.execute("UPDATE stats SET value = 0")
            conn.commit()

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, entries, size_bytes
        """
        with sqlite3.connect(self.path) as conn:
            # Get hit/miss counts
            cursor = conn.execute("SELECT key, value FROM stats")
            stats_dict = dict(cursor.fetchall())

            # Get entry count
            cursor = conn.execute("SELECT COUNT(*) FROM cache")
            entry_count = cursor.fetchone()[0]

            # Get models breakdown
            cursor = conn.execute(
                "SELECT model, COUNT(*) FROM cache GROUP BY model"
            )
            by_model = dict(cursor.fetchall())

        # Get file size
        size_bytes = self.path.stat().st_size if self.path.exists() else 0

        hits = stats_dict.get("hits", 0)
        misses = stats_dict.get("misses", 0)
        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hit_rate,
            "entries": entry_count,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "by_model": by_model,
            "path": str(self.path),
        }

    def export_db(self, output_path: Path):
        """Export the cache database to a file."""
        import shutil
        shutil.copy2(self.path, output_path)

    def import_db(self, input_path: Path):
        """Import a cache database from a file."""
        import shutil
        shutil.copy2(input_path, self.path)
