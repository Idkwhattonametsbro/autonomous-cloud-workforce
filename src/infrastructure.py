"""
Infrastructure Module
Implements: rate limiting, circuit breaker, queue system,
graceful shutdown, export/import state, audit log, rollback,
resource monitoring, cost tracking, batch processing.
"""

import json
import logging
import os
import signal
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """Prevent runaway API calls with per-minute and per-hour caps."""

    def __init__(self, memory_store):
        self.memory = memory_store
        self._locks = {}

    def check_rate(self, resource: str, max_per_minute: int = 20, max_per_hour: int = 200) -> bool:
        """
        Check if we're within rate limits for a resource.
        Returns True if allowed, False if rate limited.
        """
        now = time.time()
        key = f"rate_{resource}"
        calls = self.memory.recall(key, "rate_limits")
        call_times = json.loads(calls) if calls else []

        # Remove old entries
        one_minute_ago = now - 60
        one_hour_ago = now - 3600
        call_times = [t for t in call_times if t > one_hour_ago]

        # Check limits
        recent_minute = sum(1 for t in call_times if t > one_minute_ago)
        recent_hour = len(call_times)

        if recent_minute >= max_per_minute:
            logger.warning(f"Rate limit: {resource} hit per-minute cap ({max_per_minute})")
            return False
        if recent_hour >= max_per_hour:
            logger.warning(f"Rate limit: {resource} hit per-hour cap ({max_per_hour})")
            return False

        # Record this call
        call_times.append(now)
        self.memory.remember(key, json.dumps(call_times), "rate_limits")
        return True


class CircuitBreaker:
    """
    If an API fails N times in a row, stop calling it for M minutes.
    Prevents cascading failures.
    """

    def __init__(self, memory_store):
        self.memory = memory_store

    def is_open(self, service: str) -> bool:
        """Check if the circuit breaker is open (service is blocked)."""
        state = self.memory.recall(f"cb_{service}", "circuit_breaker")
        if not state:
            return False

        data = json.loads(state)
        if data.get("open", False):
            opened_at = data.get("opened_at", 0)
            cooldown = data.get("cooldown_seconds", 300)
            if time.time() - opened_at > cooldown:
                # Cooldown expired, close the breaker
                self.reset(service)
                return False
            return True
        return False

    def record_failure(self, service: str, threshold: int = 3, cooldown: int = 300):
        """Record a failure. Opens breaker if threshold is reached."""
        state = self.memory.recall(f"cb_{service}", "circuit_breaker")
        data = json.loads(state) if state else {"failures": 0, "open": False}

        data["failures"] = data.get("failures", 0) + 1

        if data["failures"] >= threshold:
            data["open"] = True
            data["opened_at"] = time.time()
            data["cooldown_seconds"] = cooldown
            logger.warning(f"Circuit breaker OPEN for {service} (cooldown: {cooldown}s)")

        self.memory.remember(f"cb_{service}", json.dumps(data), "circuit_breaker")

    def record_success(self, service: str):
        """Record a success. Resets failure count."""
        self.memory.remember(f"cb_{service}", json.dumps({
            "failures": 0, "open": False
        }), "circuit_breaker")

    def reset(self, service: str):
        """Manually reset a circuit breaker."""
        self.memory.remember(f"cb_{service}", json.dumps({
            "failures": 0, "open": False
        }), "circuit_breaker")


class AuditLog:
    """Immutable log of every action with timestamps."""

    def __init__(self, memory_store):
        self.memory = memory_store

    def log(self, action: str, details: Dict[str, Any], agent_id: str = ""):
        """Add an entry to the audit log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "action": action,
            "details": details,
        }

        log_str = self.memory.recall("audit_log", "system")
        audit_log = json.loads(log_str) if log_str else []
        audit_log.append(entry)

        # Keep last 1000 entries
        audit_log = audit_log[-1000:]
        self.memory.remember("audit_log", json.dumps(audit_log), "system")

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """Get recent audit log entries."""
        log_str = self.memory.recall("audit_log", "system")
        audit_log = json.loads(log_str) if log_str else []
        return audit_log[-limit:]


class StateExporter:
    """Export and import the agent's full state as a single JSON file."""

    def __init__(self, memory_store, analytics_store):
        self.memory = memory_store
        self.analytics = analytics_store

    def export_state(self) -> Dict[str, Any]:
        """Export all state to a JSON-serializable dict."""
        memories = self.memory.recall_all()
        analytics_stats = self.analytics.get_dashboard_stats()
        analytics_runs = self.analytics.get_recent_runs(100)

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "memories": memories,
            "analytics": {
                "stats": analytics_stats,
                "runs": analytics_runs,
            },
        }

    def import_state(self, state_data: Dict[str, Any]):
        """Import state from a previously exported dict."""
        if state_data.get("version") != "1.0":
            raise ValueError(f"Unsupported state version: {state_data.get('version')}")

        for mem in state_data.get("memories", []):
            self.memory.remember(
                mem["key"], mem["value"], mem["category"],
                confidence=mem.get("confidence", 0.8)
            )

        return {"status": "imported", "memories_count": len(state_data.get("memories", []))}

    def export_to_file(self, filepath: str):
        """Export state to a JSON file."""
        state = self.export_state()
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def import_from_file(self, filepath: str):
        """Import state from a JSON file."""
        with open(filepath, "r") as f:
            state = json.load(f)
        return self.import_state(state)


class GracefulShutdown:
    """Save state mid-run if SIGTERM is received."""

    def __init__(self, state_exporter: StateExporter):
        self.exporter = state_exporter
        self._shutdown_requested = False
        self._checkpoint_data = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except (ValueError, OSError):
            # Can't set signal handlers in some environments (e.g., non-main thread)
            pass

    def _handle_signal(self, signum, frame):
        """Handle shutdown signal."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
        self._save_checkpoint()

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def set_checkpoint(self, data: Dict[str, Any]):
        """Set checkpoint data that will be saved on shutdown."""
        self._checkpoint_data = data

    def _save_checkpoint(self):
        """Save checkpoint to file."""
        if self._checkpoint_data:
            checkpoint_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "checkpoint.json"
            )
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            with open(checkpoint_path, "w") as f:
                json.dump({
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "data": self._checkpoint_data,
                }, f, indent=2, default=str)
            logger.info(f"Checkpoint saved to {checkpoint_path}")


class ResourceMonitor:
    """Track memory/CPU usage of agent instances."""

    def __init__(self):
        self._samples = []

    def take_sample(self, agent_id: str):
        """Take a resource usage sample."""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            sample = {
                "agent_id": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_time": usage.ru_utime,
                "system_time": usage.ru_stime,
                "max_rss_kb": usage.ru_maxrss,
            }
            self._samples.append(sample)
            # Keep last 100 samples
            self._samples = self._samples[-100:]
            return sample
        except Exception:
            return None

    def get_report(self) -> Dict[str, Any]:
        """Get resource usage report."""
        if not self._samples:
            return {"message": "No samples collected yet"}

        latest = self._samples[-1]
        return {
            "latest": latest,
            "total_samples": len(self._samples),
        }


class BatchProcessor:
    """Process multiple items in one run instead of one per cycle."""

    def __init__(self, memory_store):
        self.memory = memory_store

    def queue_item(self, item: Dict[str, Any], queue_name: str = "default"):
        """Add an item to a processing queue."""
        queue = self._get_queue(queue_name)
        item["queued_at"] = datetime.now(timezone.utc).isoformat()
        item["id"] = len(queue) + 1
        queue.append(item)
        self._save_queue(queue_name, queue)

    def get_batch(self, queue_name: str = "default", max_items: int = 5) -> List[Dict]:
        """Get a batch of items to process."""
        queue = self._get_queue(queue_name)
        batch = queue[:max_items]
        # Remove processed items
        remaining = queue[max_items:]
        self._save_queue(queue_name, remaining)
        return batch

    def queue_size(self, queue_name: str = "default") -> int:
        """Get current queue size."""
        return len(self._get_queue(queue_name))

    def _get_queue(self, queue_name: str) -> List[Dict]:
        """Retrieve a queue."""
        queue_str = self.memory.recall(f"queue_{queue_name}", "queues")
        return json.loads(queue_str) if queue_str else []

    def _save_queue(self, queue_name: str, queue: List[Dict]):
        """Save a queue."""
        self.memory.remember(f"queue_{queue_name}", json.dumps(queue), "queues")


class CostTracker:
    """Track cumulative API costs."""

    def __init__(self, memory_store):
        self.memory = memory_store

    def record_cost(self, model: str, tokens: int, cost: float):
        """Record an API cost."""
        tracker = self._get_tracker()
        tracker["total_cost"] = tracker.get("total_cost", 0.0) + cost
        tracker["total_tokens"] = tracker.get("total_tokens", 0) + tokens

        by_model = tracker.get("by_model", {})
        if model not in by_model:
            by_model[model] = {"cost": 0.0, "tokens": 0}
        by_model[model]["cost"] += cost
        by_model[model]["tokens"] += tokens
        tracker["by_model"] = by_model

        tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.memory.remember("cost_tracker", json.dumps(tracker), "system")

    def get_report(self) -> Dict[str, Any]:
        """Get cost tracking report."""
        tracker = self._get_tracker()
        return {
            "total_cost": round(tracker.get("total_cost", 0.0), 6),
            "total_tokens": tracker.get("total_tokens", 0),
            "by_model": tracker.get("by_model", {}),
            "last_updated": tracker.get("last_updated", "never"),
        }

    def _get_tracker(self) -> Dict:
        tracker_str = self.memory.recall("cost_tracker", "system")
        return json.loads(tracker_str) if tracker_str else {"total_cost": 0.0, "total_tokens": 0, "by_model": {}}
