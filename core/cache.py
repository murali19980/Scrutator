"""
SQLite-based cache for search results to reduce API calls.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class SearchCache:
    """
    Thread-safe search result cache using SQLite.
    
    Features:
    - Store search results by query + source
    - TTL-based expiration (7 days default)
    - Automatic cleanup of old entries
    """
    
    def __init__(self, db_path: str = "search_cache.db", ttl_days: int = 7):
        self.db_path = db_path
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database with the required table."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    source TEXT NOT NULL,
                    results TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(query, source)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query_source ON search_cache(query, source)")
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache database: {e}")
        finally:
            conn.close()
    
    def get(self, query: str, source: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached results for a query and source.
        
        Returns:
            List of results if found and not expired, None otherwise.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT results, created_at FROM search_cache
                WHERE query = ? AND source = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (query, source)
            )
            row = cur.fetchone()
            if row:
                results_json, created_at = row
                created_time = datetime.fromisoformat(created_at)
                if (datetime.now() - created_time).total_seconds() < self.ttl_seconds:
                    return json.loads(results_json)
                else:
                    # Delete expired entry
                    conn.execute(
                        "DELETE FROM search_cache WHERE query = ? AND source = ?",
                        (query, source)
                    )
                    conn.commit()
            return None
        except Exception as e:
            logger.warning(f"Failed to get from cache: {e}")
            return None
        finally:
            conn.close()
    
    def set(self, query: str, source: str, results: List[Dict[str, Any]]) -> None:
        """Store search results in the cache."""
        conn = sqlite3.connect(self.db_path)
        try:
            results_json = json.dumps(results)
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache (query, source, results, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (query, source, results_json, datetime.now().isoformat())
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to set to cache: {e}")
        finally:
            conn.close()
    
    def clear_expired(self) -> int:
        """Remove all expired entries. Returns count of deleted entries."""
        conn = sqlite3.connect(self.db_path)
        try:
            expiry_time = datetime.now() - timedelta(seconds=self.ttl_seconds)
            cur = conn.execute(
                "DELETE FROM search_cache WHERE created_at < ?",
                (expiry_time.isoformat(),)
            )
            conn.commit()
            return cur.rowcount
        except Exception as e:
            logger.warning(f"Failed to clear expired cache entries: {e}")
            return 0
        finally:
            conn.close()
    
    def clear_all(self) -> None:
        """Clear the entire cache."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM search_cache")
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to clear search cache: {e}")
        finally:
            conn.close()
