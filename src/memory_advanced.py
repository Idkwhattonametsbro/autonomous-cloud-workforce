"""
Advanced Memory Module
Implements: episodic memory, forgetting curve, memory consolidation,
emotional tagging, knowledge graph, user preferences, semantic search,
memory versioning, cross-session learning, mistake journal.
"""

import json
import logging
import math
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class AdvancedMemory:
    """Enhanced memory capabilities with learning and evolution."""

    def __init__(self, memory_store):
        self.memory = memory_store

    def store_episode(self, episode: Dict[str, Any]):
        """
        Store a complete episode (goal, actions, results, outcome).
        Episodes are richer than simple key-value memories.
        """
        episodes = self._get_episodes()
        episode["id"] = len(episodes) + 1
        episode["timestamp"] = datetime.now(timezone.utc).isoformat()
        episode["access_count"] = 0
        episode["last_accessed"] = episode["timestamp"]
        episodes.append(episode)

        # Keep last 100 episodes
        episodes = episodes[-100:]
        self.memory.remember("episodes", json.dumps(episodes), "episodic_memory")

    def _get_episodes(self) -> List[Dict]:
        """Retrieve all episodes."""
        episodes_str = self.memory.recall("episodes", "episodic_memory")
        return json.loads(episodes_str) if episodes_str else []

    def recall_similar_episodes(self, goal: str, limit: int = 3) -> List[Dict]:
        """
        Find episodes similar to the current goal.
        Uses simple keyword overlap for similarity.
        """
        episodes = self._get_episodes()
        goal_words = set(goal.lower().split())

        scored = []
        for ep in episodes:
            ep_words = set(ep.get("goal", "").lower().split())
            overlap = len(goal_words & ep_words)
            similarity = overlap / max(1, len(goal_words | ep_words))
            scored.append((similarity, ep))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [ep for _, ep in scored[:limit]]

    def apply_forgetting_curve(self):
        """
        Reduce confidence of old, unaccessed memories.
        Implements Ebbinghaus forgetting curve: R = e^(-t/S)
        where R = retention, t = time, S = stability.
        """
        memories = self.memory.recall_all()
        now = datetime.now(timezone.utc)

        for mem in memories:
            if mem.get("category") in ("episodic_memory", "performance"):
                continue  # Skip special categories

            created = datetime.fromisoformat(mem["created_at"].replace("Z", "+00:00"))
            last_accessed_str = mem.get("last_accessed", mem["created_at"])
            last_accessed = datetime.fromisoformat(last_accessed_str.replace("Z", "+00:00"))

            days_since_access = (now - last_accessed).days
            access_count = mem.get("access_count", 0)

            # Stability increases with access count
            stability = 1 + (access_count * 2)

            # Retention decays over time
            retention = math.exp(-days_since_access / stability)

            # Update confidence
            new_confidence = mem.get("confidence", 0.8) * retention
            if new_confidence < 0.1:
                # Memory too weak, remove it
                self.memory.forget(mem["key"], mem["category"])
            elif new_confidence < mem.get("confidence", 0.8) * 0.9:
                # Significant decay, update
                self.memory.remember(
                    mem["key"], mem["value"], mem["category"],
                    confidence=new_confidence
                )

    def consolidate_memories(self):
        """
        Merge similar memories to keep the store clean.
        E.g., multiple "client prefers email" -> single consolidated memory.
        """
        memories = self.memory.recall_all()
        by_category = {}

        for mem in memories:
            cat = mem["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mem)

        for cat, mems in by_category.items():
            if len(mems) > 10:
                # Too many memories in this category, consolidate
                # Group by key prefix
                by_prefix = {}
                for mem in mems:
                    prefix = mem["key"].split("_")[0]
                    if prefix not in by_prefix:
                        by_prefix[prefix] = []
                    by_prefix[prefix].append(mem)

                for prefix, group in by_prefix.items():
                    if len(group) > 5:
                        # Consolidate: keep the most recent, delete others
                        group.sort(key=lambda x: x["created_at"], reverse=True)
                        for mem in group[1:]:
                            self.memory.forget(mem["key"], cat)

    def tag_emotional(self, key: str, category: str, emotion: str):
        """
        Tag a memory with emotional context (urgent, routine, failed, success).
        Helps prioritize recall.
        """
        value = self.memory.recall(key, category)
        if value:
            # Append emotion tag to value
            tagged_value = f"{value} [emotion:{emotion}]"
            self.memory.remember(key, tagged_value, category)

    def store_mistake(self, mistake: Dict[str, Any]):
        """
        Log a mistake with context so it's never repeated.
        """
        mistakes = self._get_mistakes()
        mistake["id"] = len(mistakes) + 1
        mistake["timestamp"] = datetime.now(timezone.utc).isoformat()
        mistakes.append(mistake)

        # Keep last 50 mistakes
        mistakes = mistakes[-50:]
        self.memory.remember("mistakes", json.dumps(mistakes), "mistake_journal")

    def _get_mistakes(self) -> List[Dict]:
        """Retrieve all logged mistakes."""
        mistakes_str = self.memory.recall("mistakes", "mistake_journal")
        return json.loads(mistakes_str) if mistakes_str else []

    def check_mistake_pattern(self, current_context: str) -> Optional[Dict]:
        """
        Check if current context matches a past mistake.
        Returns the mistake if found, None otherwise.
        """
        mistakes = self._get_mistakes()
        context_words = set(current_context.lower().split())

        for mistake in mistakes:
            mistake_context = mistake.get("context", "").lower()
            mistake_words = set(mistake_context.split())
            overlap = len(context_words & mistake_words)
            if overlap > len(context_words) * 0.5:
                return mistake

        return None

    def store_user_preference(self, user_id: str, preference: Dict[str, Any]):
        """
        Store user-specific preferences (communication style, topics, etc.).
        """
        key = f"user_pref_{user_id}"
        existing = self.memory.recall(key, "user_preferences")
        prefs = json.loads(existing) if existing else {}
        prefs.update(preference)
        self.memory.remember(key, json.dumps(prefs), "user_preferences")

    def get_user_preference(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user preferences."""
        key = f"user_pref_{user_id}"
        prefs_str = self.memory.recall(key, "user_preferences")
        return json.loads(prefs_str) if prefs_str else {}

    def build_knowledge_graph(self):
        """
        Build a simple knowledge graph from memories.
        Entities: clients, projects, topics.
        Relationships: worked_on, prefers, related_to.
        """
        graph = {"nodes": [], "edges": []}
        memories = self.memory.recall_all()

        for mem in memories:
            if mem["category"] == "clients":
                graph["nodes"].append({
                    "id": mem["key"],
                    "type": "client",
                    "label": mem["value"],
                })
            elif mem["category"] == "projects":
                graph["nodes"].append({
                    "id": mem["key"],
                    "type": "project",
                    "label": mem["value"],
                })

        # TODO: Add edge detection based on memory co-occurrence
        self.memory.remember("knowledge_graph", json.dumps(graph), "graph")

    def version_memory(self, key: str, category: str, new_value: str):
        """
        Keep history of how a memory changed over time.
        """
        versions = self._get_versions(key, category)
        versions.append({
            "value": new_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 10 versions
        versions = versions[-10:]
        self.memory.remember(f"versions_{key}", json.dumps(versions), f"{category}_versions")

    def _get_versions(self, key: str, category: str) -> List[Dict]:
        """Retrieve version history for a memory."""
        versions_str = self.memory.recall(f"versions_{key}", f"{category}_versions")
        return json.loads(versions_str) if versions_str else []

    def cross_session_learn(self, current_run_results: Dict):
        """
        Carry learnings from this run to inform the next run.
        """
        # Store run summary
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": current_run_results.get("goal", ""),
            "completed": current_run_results.get("completed", False),
            "iterations": current_run_results.get("iterations", 0),
            "duration": current_run_results.get("elapsed_seconds", 0),
        }

        history = self.memory.recall("run_history", "learning")
        run_history = json.loads(history) if history else []
        run_history.append(summary)
        run_history = run_history[-20:]  # Keep last 20 runs

        self.memory.remember("run_history", json.dumps(run_history), "learning")

        # Extract patterns
        if len(run_history) >= 3:
            avg_iterations = sum(r["iterations"] for r in run_history[-5:]) / 5
            success_rate = sum(1 for r in run_history[-5:] if r["completed"]) / 5

            self.memory.remember(
                "performance_baseline",
                json.dumps({"avg_iterations": avg_iterations, "success_rate": success_rate}),
                "learning"
            )
