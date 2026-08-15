#!/usr/bin/env python3
"""
Tests for the Dashboard server — API endpoints, SocketIO events, state, memory, analytics.
"""

import json
import os
import sys
import unittest
import threading
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["GROQ_API_KEY"] = "demo-key"
os.environ["OPENROUTER_API_KEY"] = "demo-key"
os.environ["DASHBOARD_PASSWORD"] = ""


class TestDashboardAPI(unittest.TestCase):
    """Test the dashboard HTTP API endpoints."""

    @classmethod
    def setUpClass(cls):
        from dashboard.app import app, socketio, state
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls.state = state

    def setUp(self):
        with self.state.lock:
            for inst in self.state.agents.values():
                inst.status = "idle"
                inst.goal = ""
                inst.iteration = 0
                inst.start_time = None
                inst.events.clear()
                inst.tools_used = {}
                inst.agent = None
            self.state.chat_history.clear()
            self.state.total_runs = 0
            self.state.total_iterations = 0

    def test_index_returns_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"html", resp.data.lower())

    def test_status_endpoint(self):
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertIn("goal", data)
        self.assertIn("agents", data)
        self.assertIn("memory_stats", data)
        self.assertEqual(data["status"], "idle")

    def test_events_endpoint_empty(self):
        resp = self.client.get("/api/events")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

    def test_tools_endpoint(self):
        resp = self.client.get("/api/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_start_conflict(self):
        """Verify 409 when primary agent is busy."""
        from dashboard.app import AgentInstance
        with self.state.lock:
            aid = "conflict-test"
            self.state.primary_id = aid
            self.state.agents[aid] = AgentInstance(aid, "test")
            self.state.agents[aid].status = "running"
        resp = self.client.post("/api/start",
            data=json.dumps({"goal": "Test", "demo": True}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 409)
        with self.state.lock:
            del self.state.agents[aid]
            self.state.primary_id = None

    def test_chat_endpoint(self):
        resp = self.client.post("/api/chat",
            data=json.dumps({"message": "Hello!"}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("response", data)
        self.assertTrue(len(data["response"]) > 0)

    def test_chat_empty_message(self):
        resp = self.client.post("/api/chat",
            data=json.dumps({"message": ""}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_chat_history(self):
        self.client.post("/api/chat",
            data=json.dumps({"message": "Hi"}),
            content_type="application/json")
        resp = self.client.get("/api/chat/history")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreater(len(data), 0)

    def test_config_get(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("max_iterations", data)

    def test_config_update(self):
        resp = self.client.post("/api/config",
            data=json.dumps({"max_iterations": 20}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)


class TestMultiAgentAPI(unittest.TestCase):
    """Test multi-agent orchestration endpoints."""

    @classmethod
    def setUpClass(cls):
        from dashboard.app import app, state
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls.state = state

    def test_list_agents(self):
        resp = self.client.get("/api/agents")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)

    def test_spawn_agent(self):
        resp = self.client.post("/api/agents",
            data=json.dumps({"goal": "Research task"}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("agent_id", data)
        self.assertEqual(data["status"], "created")

    def test_agent_events_by_id(self):
        # Spawn an agent first
        resp = self.client.post("/api/agents",
            data=json.dumps({"goal": "Test"}),
            content_type="application/json")
        agent_id = resp.get_json()["agent_id"]
        resp = self.client.get(f"/api/events/{agent_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)

    def test_agent_events_unknown_id(self):
        resp = self.client.get("/api/events/nonexistent")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])


class TestChatResponses(unittest.TestCase):
    """Test the smart chat response system."""

    def test_greeting_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("hello")
        self.assertTrue(len(resp) > 0)
        greeting_words = ["hey", "hello", "ready", "hi"]
        self.assertTrue(any(w in resp.lower() for w in greeting_words))

    def test_status_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("what's your status?")
        self.assertTrue(len(resp) > 0)
        self.assertTrue(any(w in resp.lower() for w in ["idle", "running", "thinking", "working"]))

    def test_capability_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("what can you do?")
        self.assertIn("Scan Inbox", resp)

    def test_memory_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("tell me about your memory")
        self.assertIn("memories", resp.lower())

    def test_analytics_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("show me analytics")
        self.assertIn("runs", resp.lower())

    def test_default_response(self):
        from dashboard.app import get_chat_response
        resp = get_chat_response("process the quarterly report for Acme Corp")
        self.assertTrue(len(resp) > 0)

    def test_responses_vary(self):
        from dashboard.app import get_chat_response
        responses = set()
        for _ in range(10):
            responses.add(get_chat_response("something random xyz"))
        self.assertGreater(len(responses), 1)


class TestPersistentMemory(unittest.TestCase):
    """Test the SQLite memory store."""

    def setUp(self):
        import tempfile
        self.db_path = tempfile.mktemp(suffix=".db")
        from dashboard.memory import MemoryStore
        self.mem = MemoryStore(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_remember_and_recall(self):
        self.mem.remember("client_name", "Acme Corp", "clients")
        val = self.mem.recall("client_name", "clients")
        self.assertEqual(val, "Acme Corp")

    def test_recall_missing(self):
        val = self.mem.recall("nonexistent", "test")
        self.assertIsNone(val)

    def test_overwrite(self):
        self.mem.remember("key", "old", "cat")
        self.mem.remember("key", "new", "cat")
        self.assertEqual(self.mem.recall("key", "cat"), "new")

    def test_forget(self):
        self.mem.remember("key", "val", "cat")
        self.mem.forget("key", "cat")
        self.assertIsNone(self.mem.recall("key", "cat"))

    def test_recall_category(self):
        self.mem.remember("a", "1", "test")
        self.mem.remember("b", "2", "test")
        self.mem.remember("c", "3", "other")
        results = self.mem.recall_category("test")
        self.assertEqual(len(results), 2)

    def test_search(self):
        self.mem.remember("client_acme", "Pricing inquiry", "clients")
        results = self.mem.search_memories("acme")
        self.assertGreater(len(results), 0)

    def test_stats(self):
        self.mem.remember("a", "1", "cat1")
        self.mem.remember("b", "2", "cat2")
        stats = self.mem.get_stats()
        self.assertEqual(stats["total_memories"], 2)
        self.assertIn("cat1", stats["categories"])

    def test_log_interaction(self):
        self.mem.log_interaction("user", "Hello")
        self.mem.log_interaction("assistant", "Hi there")
        history = self.mem.get_recent_interactions()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")


class TestAnalytics(unittest.TestCase):
    """Test the analytics store."""

    def setUp(self):
        import tempfile
        self.db_path = tempfile.mktemp(suffix=".db")
        from dashboard.analytics import AnalyticsStore
        self.store = AnalyticsStore(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_record_and_fetch_run(self):
        run_id = self.store.record_run("Test goal", "completed", 5, 10.5, {"scan_inbox": 2})
        runs = self.store.get_recent_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["goal"], "Test goal")
        self.assertEqual(runs[0]["iterations"], 5)

    def test_dashboard_stats(self):
        self.store.record_run("Goal 1", "completed", 3, 5.0, {"tool_a": 1})
        self.store.record_run("Goal 2", "completed", 5, 8.0, {"tool_b": 2})
        stats = self.store.get_dashboard_stats()
        self.assertEqual(stats["total_runs"], 2)
        self.assertEqual(stats["success_rate"], 100.0)

    def test_tool_usage(self):
        run_id = self.store.record_run("Test", "completed", 1, 1.0, {})
        self.store.record_tool_usage("scan_inbox", run_id, 0.5, True)
        self.store.record_tool_usage("scan_inbox", run_id, 0.3, True)
        stats = self.store.get_dashboard_stats()
        self.assertGreater(len(stats["top_tools"]), 0)

    def test_duration_trend(self):
        for i in range(5):
            self.store.record_run(f"Goal {i}", "completed", i+1, float(i+1)*2, {})
        stats = self.store.get_dashboard_stats()
        self.assertEqual(len(stats["duration_trend"]), 5)


class TestDashboardState(unittest.TestCase):
    """Test the multi-agent state container."""

    def test_initial_state(self):
        from dashboard.app import DashboardState
        s = DashboardState()
        self.assertEqual(s.total_runs, 0)
        self.assertEqual(len(s.agents), 0)
        self.assertIsNone(s.primary_id)

    def test_thread_safety(self):
        from dashboard.app import DashboardState, AgentInstance
        s = DashboardState()
        errors = []

        def modify(n):
            try:
                for i in range(100):
                    with s.lock:
                        s.total_runs += 1
                        aid = f"agent-{n}-{i}"
                        s.agents[aid] = AgentInstance(aid, f"Goal {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=modify, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(s.total_runs, 500)
        self.assertEqual(len(s.agents), 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
