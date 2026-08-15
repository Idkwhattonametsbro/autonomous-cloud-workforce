"""
Persistent Memory Module — SQLite-based long-term memory for the agent.
Stores facts, preferences, and learnings across runs.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory.db")


class MemoryStore:
    """SQLite-backed memory store for agent persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'general',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.8,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    UNIQUE(category, key)
                );
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    goal TEXT DEFAULT '',
                    agent_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category);
                CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at);
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ─── Memory Operations ───

    def remember(self, key: str, value: str, category: str = "general",
                 source: str = "", confidence: float = 0.8) -> bool:
        """Store a memory. Overwrites if key already exists in category."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO memories (category, key, value, source, confidence, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(category, key) DO UPDATE SET
                        value=excluded.value, source=excluded.source,
                        confidence=excluded.confidence, updated_at=excluded.updated_at
                """, (category, key, value, source, confidence, now, now))
            return True
        except Exception as e:
            logger.error(f"Memory store failed: {e}")
            return False

    def recall(self, key: str, category: str = "general") -> Optional[str]:
        """Retrieve a specific memory by key and category."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM memories WHERE category=? AND key=?",
                (category, key)
            ).fetchone()
            if row:
                # Increment access count
                conn.execute(
                    "UPDATE memories SET access_count=access_count+1 WHERE category=? AND key=?",
                    (category, key)
                )
                return row[0]
        return None

    def recall_category(self, category: str, limit: int = 20) -> List[Dict]:
        """Retrieve all memories in a category."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, value, source, confidence, created_at, access_count "
                "FROM memories WHERE category=? ORDER BY access_count DESC LIMIT ?",
                (category, limit)
            ).fetchall()
            return [
                {"key": r[0], "value": r[1], "source": r[2],
                 "confidence": r[3], "created_at": r[4], "access_count": r[5]}
                for r in rows
            ]

    def forget(self, key: str, category: str = "general") -> bool:
        """Delete a specific memory."""
        with self._conn() as conn:
            conn.execute("DELETE FROM memories WHERE category=? AND key=?", (category, key))
        return True

    def search_memories(self, query: str, limit: int = 10) -> List[Dict]:
        """Simple keyword search across all memories."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT category, key, value, confidence FROM memories "
                "WHERE key LIKE ? OR value LIKE ? ORDER BY confidence DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
            return [
                {"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]}
                for r in rows
            ]

    def get_stats(self) -> Dict:
        """Get memory store statistics."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            cats = conn.execute(
                "SELECT category, COUNT(*) FROM memories GROUP BY category"
            ).fetchall()
            return {
                "total_memories": total,
                "categories": {r[0]: r[1] for r in cats},
            }

    # ─── Interaction Logging ───

    def log_interaction(self, role: str, content: str, goal: str = "", agent_id: str = ""):
        """Log a chat interaction for history."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO interactions (role, content, goal, agent_id, created_at) VALUES (?,?,?,?,?)",
                (role, content, goal, agent_id, now)
            )

    def get_recent_interactions(self, limit: int = 50) -> List[Dict]:
        """Get recent chat interactions."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, goal, created_at FROM interactions ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {"role": r[0], "content": r[1], "goal": r[2], "timestamp": r[3]}
                for r in reversed(rows)
            ]
