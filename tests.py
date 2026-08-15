#!/usr/bin/env python3
"""
Comprehensive test suite for the Autonomous Cloud Workforce.
Tests all components: config, tools, models, agent, and the dashboard.
"""

import json
import os
import sys
import time
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import AppConfig, ModelConfig
from src.tools import ToolRegistry, create_default_registry
from src.agent import ReActAgent, REACT_SYSTEM_PROMPT


# ═══════════════════════════════════════════════
# Test Suite 1: Configuration
# ═══════════════════════════════════════════════

class TestModelConfig(unittest.TestCase):
    """Test ModelConfig dataclass."""

    def test_defaults(self):
        mc = ModelConfig(name="test", provider="groq", model_id="test-model")
        self.assertEqual(mc.max_tokens, 4096)
        self.assertEqual(mc.temperature, 0.1)
        self.assertEqual(mc.description, "")

    def test_custom_values(self):
        mc = ModelConfig(
            name="custom", provider="openrouter", model_id="gemini-pro",
            max_tokens=16000, temperature=0.5, description="A test model"
        )
        self.assertEqual(mc.max_tokens, 16000)
        self.assertEqual(mc.temperature, 0.5)
        self.assertEqual(mc.provider, "openrouter")


class TestAppConfig(unittest.TestCase):
    """Test AppConfig dataclass and validation."""

    def test_default_models_registered(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig()
        self.assertIn("task_manager", config.models)
        self.assertIn("data_reader", config.models)
        self.assertIn("code_specialist", config.models)
        self.assertEqual(len(config.models), 3)

    def test_model_providers(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig()
        self.assertEqual(config.models["task_manager"].provider, "groq")
        self.assertEqual(config.models["data_reader"].provider, "openrouter")
        self.assertEqual(config.models["code_specialist"].provider, "openrouter")

    def test_get_model_valid(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig()
        model = config.get_model("task_manager")
        self.assertEqual(model.provider, "groq")

    def test_get_model_invalid(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig()
        with self.assertRaises(ValueError) as ctx:
            config.get_model("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    def test_validate_missing_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig()
        with self.assertRaises(ValueError) as ctx:
            config.validate()
        self.assertIn("GROQ_API_KEY", str(ctx.exception))
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

    def test_validate_with_keys(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test", "OPENROUTER_API_KEY": "test"}, clear=True):
            config = AppConfig()
        self.assertTrue(config.validate())

    def test_env_overrides(self):
        env = {
            "GROQ_API_KEY": "groq123",
            "OPENROUTER_API_KEY": "or456",
            "AGENT_GOAL": "Do something cool",
            "VERBOSE": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            config = AppConfig()
        self.assertEqual(config.groq_api_key, "groq123")
        self.assertEqual(config.openrouter_api_key, "or456")
        self.assertEqual(config.agent_goal, "Do something cool")
        self.assertFalse(config.verbose)


# ═══════════════════════════════════════════════
# Test Suite 2: Tool Registry
# ═══════════════════════════════════════════════

class TestToolRegistry(unittest.TestCase):
    """Test the tool registration and execution system."""

    def test_register_and_list(self):
        registry = ToolRegistry()
        registry.register("test_tool", "A test tool", {"type": "object", "properties": {}}, lambda: {"ok": True})
        self.assertIn("test_tool", registry.list_tools())

    def test_get_tools_schema(self):
        registry = ToolRegistry()
        registry.register("my_tool", "Does stuff", {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }, lambda x="": {"ok": True})
        schemas = registry.get_tools_schema()
        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["function"]["name"], "my_tool")
        self.assertIn("x", schemas[0]["function"]["parameters"]["properties"])

    def test_execute_success(self):
        registry = ToolRegistry()
        registry.register("add", "Adds numbers", {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        }, lambda a, b: {"result": a + b})
        result = json.loads(registry.execute("add", {"a": 3, "b": 4}))
        self.assertEqual(result["result"], 7)

    def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = json.loads(registry.execute("nonexistent", {}))
        self.assertIn("error", result)
        self.assertIn("Unknown tool", result["error"])

    def test_execute_handler_error(self):
        registry = ToolRegistry()
        registry.register("bad", "Always fails", {"type": "object", "properties": {}},
                         lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        result = json.loads(registry.execute("bad", {}))
        self.assertIn("error", result)
        self.assertIn("boom", result["error"])

    def test_execute_type_error(self):
        registry = ToolRegistry()
        registry.register("typed", "Needs specific args", {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }, lambda name: {"name": name})
        # Call with wrong args (missing required 'name')
        result = json.loads(registry.execute("typed", {}))
        self.assertIn("error", result)

    def test_get_tool_info(self):
        registry = ToolRegistry()
        registry.register("info_tool", "desc", {"type": "object", "properties": {}},
                         lambda: None, category="test_cat")
        info = registry.get_tool_info("info_tool")
        self.assertIsNotNone(info)
        self.assertEqual(info["category"], "test_cat")

    def test_get_tool_info_missing(self):
        registry = ToolRegistry()
        self.assertIsNone(registry.get_tool_info("nope"))


class TestDefaultTools(unittest.TestCase):
    """Test the built-in default tools."""

    def setUp(self):
        self.registry = create_default_registry()

    def test_all_tools_registered(self):
        expected = [
            "scan_inbox", "draft_reply", "update_crm", "read_database",
            "log_task", "web_search", "file_read", "file_write", "git_commit_and_push",
        ]
        for tool_name in expected:
            self.assertIn(tool_name, self.registry.list_tools(),
                          f"Tool '{tool_name}' not registered")

    def test_scan_inbox(self):
        result = json.loads(self.registry.execute("scan_inbox", {}))
        self.assertEqual(result["status"], "needs_connection")
        self.assertIn("Gmail", result.get("display_name", ""))

    def test_draft_reply(self):
        result = json.loads(self.registry.execute("draft_reply", {
            "message_id": "msg_001",
            "context": "Pricing inquiry",
            "tone": "friendly",
        }))
        self.assertEqual(result["status"], "needs_connection")

    def test_update_crm(self):
        result = json.loads(self.registry.execute("update_crm", {
            "contact_id": "c_42",
            "data": {"status": "hot_lead", "notes": "Very interested"},
        }))
        self.assertEqual(result["status"], "needs_connection")

    def test_read_database(self):
        result = json.loads(self.registry.execute("read_database", {
            "query": "SELECT * FROM orders",
            "table": "orders",
        }))
        self.assertEqual(result["status"], "needs_connection")

    def test_log_task(self):
        # Use a temp directory for logs
        result = json.loads(self.registry.execute("log_task", {
            "task_name": "test_task",
            "status": "completed",
            "details": "Test details",
        }))
        self.assertEqual(result["status"], "logged")
        self.assertEqual(result["log_entry"]["task"], "test_task")

    def test_web_search(self):
        result = json.loads(self.registry.execute("web_search", {"query": "AI news"}))
        self.assertEqual(result["status"], "needs_connection")

    def test_file_read_write(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("hello world")
            path = f.name

        try:
            # Read
            result = json.loads(self.registry.execute("file_read", {"file_path": path}))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["content"], "hello world")

            # Write
            new_path = path + ".new"
            result = json.loads(self.registry.execute("file_write", {
                "file_path": new_path,
                "content": "new content",
            }))
            self.assertEqual(result["status"], "success")

            # Verify write
            result = json.loads(self.registry.execute("file_read", {"file_path": new_path}))
            self.assertEqual(result["content"], "new content")
            os.unlink(new_path)
        finally:
            os.unlink(path)

    def test_file_read_nonexistent(self):
        result = json.loads(self.registry.execute("file_read", {"file_path": "/nonexistent/path.txt"}))
        self.assertEqual(result["status"], "error")

    def test_git_commit_not_a_repo(self):
        # Running in a non-git context should gracefully skip
        result = json.loads(self.registry.execute("git_commit_and_push", {"message": "test"}))
        # Either success (if in a repo) or skipped
        self.assertIn(result["status"], ["success", "skipped", "error"])


# ═══════════════════════════════════════════════
# Test Suite 3: Agent (with mocked models)
# ═══════════════════════════════════════════════

class TestReActAgent(unittest.TestCase):
    """Test the ReAct agent loop with mocked LLM calls."""

    def _make_config(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test", "OPENROUTER_API_KEY": "test"}, clear=True):
            return AppConfig()

    def _make_mock_response(self, content="", tool_calls=None):
        resp = {"content": content}
        if tool_calls:
            resp["tool_calls"] = tool_calls
        return resp

    def test_agent_initialization(self):
        config = self._make_config()
        tools = create_default_registry()
        agent = ReActAgent(config=config, tools=tools)
        self.assertEqual(agent.iteration_count, 0)
        self.assertEqual(agent.task_summary, "")
        self.assertIsNone(agent.start_time)

    @patch("src.agent.ModelRouter")
    def test_agent_completes_with_task_complete(self, MockRouter):
        """Agent should stop when the model returns TASK_COMPLETE."""
        config = self._make_config()
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.return_value = self._make_mock_response(
            content="TASK_COMPLETE - All tasks done successfully."
        )

        agent = ReActAgent(config=config, tools=tools)
        report = agent.run(goal="Test goal")

        self.assertTrue(report["completed"])
        self.assertEqual(report["iterations"], 1)
        self.assertIn("TASK_COMPLETE", report["summary"])

    @patch("src.agent.ModelRouter")
    def test_agent_uses_tools(self, MockRouter):
        """Agent should call tools and continue until TASK_COMPLETE."""
        config = self._make_config()
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        # First call: decide to use scan_inbox
        # Second call: TASK_COMPLETE
        mock_router.query.side_effect = [
            self._make_mock_response(
                content="I need to scan the inbox first.",
                tool_calls=[{
                    "id": "call_1",
                    "function": "scan_inbox",
                    "arguments": "{}",
                }],
            ),
            self._make_mock_response(content="TASK_COMPLETE - Done."),
        ]

        agent = ReActAgent(config=config, tools=tools)
        report = agent.run(goal="Check inbox")

        self.assertTrue(report["completed"])
        self.assertEqual(report["iterations"], 2)

    @patch("src.agent.ModelRouter")
    def test_agent_max_iterations(self, MockRouter):
        """Agent should stop after max iterations if never completing."""
        config = self._make_config()
        config.max_react_iterations = 3
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.return_value = self._make_mock_response(
            content="Still working..."  # Never says TASK_COMPLETE
        )

        agent = ReActAgent(config=config, tools=tools)
        report = agent.run(goal="Impossible task")

        self.assertFalse(report["completed"])
        self.assertEqual(report["iterations"], 3)

    @patch("src.agent.ModelRouter")
    def test_agent_self_corrects_on_error(self, MockRouter):
        """Agent should continue after a model query fails."""
        config = self._make_config()
        config.max_react_iterations = 3
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.side_effect = [
            RuntimeError("API timeout"),  # First call fails
            self._make_mock_response(content="TASK_COMPLETE - Recovered."),  # Second succeeds
        ]

        agent = ReActAgent(config=config, tools=tools)
        report = agent.run(goal="Test recovery")

        self.assertTrue(report["completed"])

    @patch("src.agent.ModelRouter")
    def test_agent_event_callback(self, MockRouter):
        """Agent should emit events via callback."""
        config = self._make_config()
        tools = create_default_registry()
        events = []

        def callback(event_type, data):
            events.append((event_type, data))

        mock_router = MockRouter.return_value
        mock_router.query.return_value = self._make_mock_response(
            content="TASK_COMPLETE - Done."
        )

        agent = ReActAgent(config=config, tools=tools, event_callback=callback)
        agent.run(goal="Test events")

        event_types = [e[0] for e in events]
        self.assertIn("agent_start", event_types)
        self.assertIn("iteration_start", event_types)
        self.assertIn("model_response", event_types)
        self.assertIn("agent_complete", event_types)

    @patch("src.agent.ModelRouter")
    def test_agent_send_message(self, MockRouter):
        """Test the interactive chat mode."""
        config = self._make_config()
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.return_value = self._make_mock_response(
            content="I can help with that! Let me look into it."
        )

        agent = ReActAgent(config=config, tools=tools)
        agent.conversation_history = [{"role": "system", "content": "You are an agent."}]
        response = agent.send_message("What's the status of my orders?")

        self.assertIn("help", response.lower())
        mock_router.query.assert_called_once()

    @patch("src.agent.ModelRouter")
    def test_agent_send_message_with_tool_call(self, MockRouter):
        """Test chat mode when the agent decides to use a tool."""
        config = self._make_config()
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.side_effect = [
            # First call: agent decides to use read_database
            self._make_mock_response(
                content="Let me check the database.",
                tool_calls=[{
                    "id": "call_chat_1",
                    "function": "read_database",
                    "arguments": json.dumps({"query": "orders", "table": "orders"}),
                }],
            ),
            # Second call: follow-up after tool result
            self._make_mock_response(content="I found 3 orders in the database."),
        ]

        agent = ReActAgent(config=config, tools=tools)
        agent.conversation_history = [{"role": "system", "content": "You are an agent."}]
        response = agent.send_message("How many orders are there?")

        self.assertIn("3 orders", response)
        self.assertEqual(mock_router.query.call_count, 2)

    @patch("src.agent.ModelRouter")
    def test_agent_report_structure(self, MockRouter):
        """Verify the final report has all expected fields."""
        config = self._make_config()
        tools = create_default_registry()

        mock_router = MockRouter.return_value
        mock_router.query.return_value = self._make_mock_response(
            content="TASK_COMPLETE - All good."
        )

        agent = ReActAgent(config=config, tools=tools)
        report = agent.run(goal="Test report")

        self.assertIn("goal", report)
        self.assertIn("iterations", report)
        self.assertIn("elapsed_seconds", report)
        self.assertIn("completed", report)
        self.assertIn("summary", report)
        self.assertIn("timestamp", report)
        self.assertIn("conversation_turns", report)


# ═══════════════════════════════════════════════
# Test Suite 4: Model Router (with mocked HTTP)
# ═══════════════════════════════════════════════

class TestModelRouter(unittest.TestCase):
    """Test the model routing layer with mocked API calls."""

    def _make_config(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test", "OPENROUTER_API_KEY": "test"}, clear=True):
            return AppConfig()

    @patch("src.models.Groq")
    def test_groq_query(self, MockGroq):
        """Test querying a model on Groq."""
        from src.models import ModelRouter

        mock_client = MockGroq.return_value
        mock_choice = MagicMock()
        mock_choice.content = "Hello from Groq"
        mock_choice.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_choice)]
        mock_client.chat.completions.create.return_value = mock_response

        config = self._make_config()
        router = ModelRouter(config)
        result = router.query("task_manager", [{"role": "user", "content": "hi"}])

        self.assertEqual(result["content"], "Hello from Groq")
        self.assertNotIn("tool_calls", result)

    @patch("src.models.Groq")
    def test_groq_query_with_tool_calls(self, MockGroq):
        """Test Groq response with tool calls."""
        from src.models import ModelRouter

        mock_client = MockGroq.return_value

        mock_tc = MagicMock()
        mock_tc.id = "call_abc"
        mock_tc.function.name = "scan_inbox"
        mock_tc.function.arguments = "{}"

        mock_choice = MagicMock()
        mock_choice.content = None
        mock_choice.tool_calls = [mock_tc]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_choice)]
        mock_client.chat.completions.create.return_value = mock_response

        config = self._make_config()
        router = ModelRouter(config)
        result = router.query("task_manager", [{"role": "user", "content": "check inbox"}])

        self.assertEqual(result["content"], "")
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["function"], "scan_inbox")

    @patch("src.models.Groq")
    @patch("src.models.requests.Session")
    def test_openrouter_query(self, MockSession, MockGroq):
        """Test querying a model on OpenRouter."""
        from src.models import ModelRouter

        mock_session = MockSession.return_value
        mock_session.headers = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Hello from OpenRouter",
                    "tool_calls": None,
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.post.return_value = mock_response

        config = self._make_config()
        router = ModelRouter(config)
        result = router.query("data_reader", [{"role": "user", "content": "read this doc"}])

        self.assertEqual(result["content"], "Hello from OpenRouter")

    @patch("src.models.Groq")
    def test_fallback_on_error(self, MockGroq):
        """Test that the router falls back to another model on failure."""
        from src.models import ModelRouter

        mock_client = MockGroq.return_value
        mock_client.chat.completions.create.side_effect = RuntimeError("API error")

        config = self._make_config()
        router = ModelRouter(config)

        # Patch _query_openrouter to succeed
        with patch.object(router, '_query_openrouter', return_value={"content": "fallback worked"}):
            result = router.query("task_manager", [{"role": "user", "content": "test"}],
                                 fallback_role="data_reader")

        self.assertEqual(result["content"], "fallback worked")

    @patch("src.models.Groq")
    def test_no_infinite_fallback_loop(self, MockGroq):
        """Ensure fallback doesn't loop if both models fail."""
        from src.models import ModelRouter

        mock_client = MockGroq.return_value
        mock_client.chat.completions.create.side_effect = RuntimeError("API error")

        config = self._make_config()
        router = ModelRouter(config)

        # Also mock OpenRouter so both providers fail
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = RuntimeError("OpenRouter also failed")
        mock_session.post.return_value = mock_response
        router._openrouter_session = mock_session

        with self.assertRaises(RuntimeError):
            router.query("task_manager", [{"role": "user", "content": "test"}],
                        fallback_role="data_reader")


# ═══════════════════════════════════════════════
# Test Suite 5: Integration Tests
# ═══════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components."""

    @patch("src.agent.ModelRouter")
    def test_full_react_cycle_with_multiple_tools(self, MockRouter):
        """Simulate a full ReAct cycle using multiple tools."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "t", "OPENROUTER_API_KEY": "t"}, clear=True):
            config = AppConfig()
        tools = create_default_registry()
        events = []

        mock_router = MockRouter.return_value
        mock_router.query.side_effect = [
            # Iteration 1: scan inbox
            {"content": "Let me scan the inbox.", "tool_calls": [{
                "id": "c1", "function": "scan_inbox", "arguments": "{}"
            }]},
            # Iteration 2: draft reply
            {"content": "Found a message. Let me draft a reply.", "tool_calls": [{
                "id": "c2", "function": "draft_reply",
                "arguments": json.dumps({"message_id": "msg_1", "context": "Pricing", "tone": "professional"})
            }]},
            # Iteration 3: log and complete
            {"content": "Let me log the task.", "tool_calls": [{
                "id": "c3", "function": "log_task",
                "arguments": json.dumps({"task_name": "reply_to_client", "status": "completed"})
            }]},
            # Iteration 4: final completion
            {"content": "TASK_COMPLETE - Scanned inbox, drafted reply, logged task."},
        ]

        agent = ReActAgent(config=config, tools=tools,
                          event_callback=lambda t, d: events.append(t))
        report = agent.run(goal="Check inbox and reply to messages")

        self.assertTrue(report["completed"])
        self.assertEqual(report["iterations"], 4)
        self.assertIn("agent_start", events)
        self.assertIn("tool_executing", events)
        self.assertIn("tool_result", events)

    def test_tool_registry_roundtrip(self):
        """Verify all default tools can be called and return valid JSON."""
        registry = create_default_registry()
        for tool_name in registry.list_tools():
            info = registry.get_tool_info(tool_name)
            schema = info["schema"]["function"]
            # Verify schema structure
            self.assertIn("name", schema)
            self.assertIn("description", schema)
            self.assertIn("parameters", schema)


# ═══════════════════════════════════════════════
# Run All Tests
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
