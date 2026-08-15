"""
Analytics Module — Tracks historical agent performance data.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "analytics.db")


class AnalyticsStore:
    """SQLite-backed analytics for historical agent performance."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT DEFAULT '',
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    iterations INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    tools_used TEXT DEFAULT '{}',
                    model_used TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    run_id INTEGER,
                    duration_seconds REAL DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_created ON agent_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_tool_usage_created ON tool_usage(created_at);
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def record_run(self, goal: str, status: str, iterations: int,
                   duration: float, tools_used: Dict, model: str = "",
                   agent_id: str = "") -> int:
        """Record a completed agent run."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO agent_runs (agent_id, goal, status, iterations, duration_seconds, tools_used, model_used, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (agent_id, goal, status, iterations, duration, json.dumps(tools_used), model, now)
            )
            return cursor.lastrowid

    def record_tool_usage(self, tool_name: str, run_id: int, duration: float = 0, success: bool = True):
        """Record individual tool usage."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tool_usage (tool_name, run_id, duration_seconds, success, created_at) VALUES (?,?,?,?,?)",
                (tool_name, run_id, duration, 1 if success else 0, now)
            )

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats for the analytics dashboard."""
        with self._conn() as conn:
            total_runs = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
            total_iterations = conn.execute("SELECT COALESCE(SUM(iterations),0) FROM agent_runs").fetchone()[0]
            avg_duration = conn.execute("SELECT COALESCE(AVG(duration_seconds),0) FROM agent_runs").fetchone()[0]
            success_rate = 0
            if total_runs > 0:
                completed = conn.execute("SELECT COUNT(*) FROM agent_runs WHERE status='completed'").fetchone()[0]
                success_rate = round(completed / total_runs * 100, 1)

            # Last 7 days
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            runs_this_week = conn.execute(
                "SELECT COUNT(*) FROM agent_runs WHERE created_at > ?", (week_ago,)
            ).fetchone()[0]

            # Top tools
            top_tools = conn.execute(
                "SELECT tool_name, COUNT(*) as cnt FROM tool_usage GROUP BY tool_name ORDER BY cnt DESC LIMIT 5"
            ).fetchall()

            # Duration trend (last 10 runs)
            duration_trend = conn.execute(
                "SELECT duration_seconds, iterations, created_at FROM agent_runs ORDER BY id DESC LIMIT 10"
            ).fetchall()

            return {
                "total_runs": total_runs,
                "total_iterations": total_iterations,
                "avg_duration": round(avg_duration, 2),
                "success_rate": success_rate,
                "runs_this_week": runs_this_week,
                "top_tools": [{"name": r[0], "count": r[1]} for r in top_tools],
                "duration_trend": [
                    {"duration": r[0], "iterations": r[1], "time": r[2]}
                    for r in reversed(duration_trend)
                ],
            }

    def get_recent_runs(self, limit: int = 20) -> List[Dict]:
        """Get recent agent runs."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, agent_id, goal, status, iterations, duration_seconds, tools_used, created_at "
                "FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                {
                    "id": r[0], "agent_id": r[1], "goal": r[2], "status": r[3],
                    "iterations": r[4], "duration": r[5],
                    "tools_used": json.loads(r[6]) if r[6] else {},
                    "timestamp": r[7],
                }
                for r in rows
            ]
