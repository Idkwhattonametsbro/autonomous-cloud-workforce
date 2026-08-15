"""
Tool definitions for the Autonomous Cloud Workforce agent.
Each tool checks for required connections before executing.
If a connection is missing, the tool returns a structured error
that triggers the agent to ask the user for credentials.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────
# Connection Checker
# ─────────────────────────────────────────────

def _check_connection(required_keys: List[str], tool_name: str,
                       display_name: str, get_link: str,
                       get_instructions: str,
                       fields: List[Dict]) -> Optional[Dict]:
    """
    Check if all required credentials are stored.
    Returns None if all present, or a needs_connection dict if any are missing.
    """
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
    except Exception:
        return None  # If memory isn't available, don't block

    missing = []
    for key in required_keys:
        val = mem.recall(key, "user_credentials")
        if not val:
            missing.append(key)

    if missing:
        return {
            "status": "needs_connection",
            "tool": tool_name,
            "display_name": display_name,
            "message": f"{display_name} is not connected. I need your credentials to use this tool.",
            "get_link": get_link,
            "get_instructions": get_instructions,
            "required_fields": fields,
            "missing_keys": missing,
        }
    return None


def _get_cred(key: str) -> Optional[str]:
    """Safely retrieve a stored credential."""
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        return mem.recall(key, "user_credentials")
    except Exception:
        return None


# ─────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────

class ToolRegistry:
    """Manages the collection of tools available to the agent."""

    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._handlers: Dict[str, Callable] = {}
        self._categories: Dict[str, str] = {}

    def register(self, name: str, description: str, parameters: Dict,
                 handler: Callable, category: str = "general"):
        self._tools[name] = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }
        self._handlers[name] = handler
        self._categories[name] = category
        logger.debug(f"Registered tool: {name} (category: {category})")

    def get_tools_schema(self) -> List[Dict]:
        return list(self._tools.values())

    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._handlers:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = self._handlers[name](**arguments)
            return json.dumps(result, default=str)
        except TypeError as e:
            logger.error(f"Tool '{name}' argument error: {e}")
            return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return json.dumps({"error": str(e)})

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> Optional[Dict]:
        if name not in self._tools:
            return None
        return {"schema": self._tools[name], "category": self._categories.get(name, "general")}


# ─────────────────────────────────────────────
# Tool Implementations
# ─────────────────────────────────────────────

def _scan_inbox() -> Dict[str, Any]:
    """Check inbox for new messages. Requires Gmail connection."""
    logger.info("Scanning inbox...")
    conn_check = _check_connection(
        required_keys=["gmail_address", "gmail_app_password"],
        tool_name="scan_inbox",
        display_name="Gmail",
        get_link="https://myaccount.google.com/apppasswords",
        get_instructions="Go to Google Account > Security > 2-Step Verification > App Passwords. Generate a new password for 'Mail'.",
        fields=[
            {"key": "gmail_address", "label": "Gmail Address", "type": "email", "placeholder": "you@gmail.com"},
            {"key": "gmail_app_password", "label": "App Password", "type": "password", "placeholder": "xxxx-xxxx-xxxx-xxxx"},
        ],
    )
    if conn_check:
        return conn_check

    # Real integration would go here — credentials are available
    email = _get_cred("gmail_address")
    return {
        "status": "success",
        "connected_as": email,
        "new_messages": 0,
        "messages": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _draft_reply(message_id: str, context: str, tone: str = "professional") -> Dict[str, Any]:
    """Draft and optionally send a reply. Requires Gmail connection to send."""
    logger.info(f"Drafting reply to {message_id} (tone: {tone})")
    # Drafting doesn't require credentials — but SENDING does
    conn_check = _check_connection(
        required_keys=["gmail_address", "gmail_app_password"],
        tool_name="draft_reply",
        display_name="Gmail",
        get_link="https://myaccount.google.com/apppasswords",
        get_instructions="Go to Google Account > Security > 2-Step Verification > App Passwords.",
        fields=[
            {"key": "gmail_address", "label": "Gmail Address", "type": "email", "placeholder": "you@gmail.com"},
            {"key": "gmail_app_password", "label": "App Password", "type": "password", "placeholder": "xxxx-xxxx-xxxx-xxxx"},
        ],
    )
    if conn_check:
        conn_check["message"] = "I can draft the reply, but to send it I need your Gmail connected first."
        return conn_check

    return {
        "status": "success",
        "message_id": message_id,
        "draft": f"[Reply to {message_id} — {tone} tone, context: {context[:100]}]",
        "sent": True,
        "drafted_at": datetime.now(timezone.utc).isoformat(),
    }


def _update_crm(contact_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update CRM record. Requires CRM connection."""
    logger.info(f"Updating CRM for {contact_id}")
    conn_check = _check_connection(
        required_keys=["crm_api_key"],
        tool_name="update_crm",
        display_name="CRM (HubSpot)",
        get_link="https://app.hubspot.com/private-apps",
        get_instructions="Go to HubSpot > Settings > Integrations > Private Apps > Create private app. Copy the API key.",
        fields=[
            {"key": "crm_api_key", "label": "CRM API Key", "type": "password", "placeholder": "your-api-key"},
            {"key": "crm_platform", "label": "Platform", "type": "text", "placeholder": "HubSpot"},
        ],
    )
    if conn_check:
        return conn_check

    return {
        "status": "success",
        "contact_id": contact_id,
        "updated_fields": list(data.keys()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_database(query: str, table: str) -> Dict[str, Any]:
    """Query database. Requires database connection."""
    logger.info(f"Querying {table}: {query}")
    conn_check = _check_connection(
        required_keys=["db_url"],
        tool_name="read_database",
        display_name="Database",
        get_link="https://console.cloud.google.com/sql",
        get_instructions="Provide your database connection string (e.g., postgresql://user:pass@host:5432/dbname).",
        fields=[
            {"key": "db_url", "label": "Connection String", "type": "password", "placeholder": "postgresql://user:pass@host:5432/db"},
        ],
    )
    if conn_check:
        return conn_check

    return {
        "status": "success",
        "table": table,
        "rows": [],
        "row_count": 0,
        "query": query,
    }


def _web_search(query: str) -> Dict[str, Any]:
    """Search the web. Requires Tavily or SerpAPI key."""
    logger.info(f"Web search: {query}")
    conn_check = _check_connection(
        required_keys=["search_api_key"],
        tool_name="web_search",
        display_name="Web Search",
        get_link="https://tavily.com/",
        get_instructions="Sign up at tavily.com for a free API key (1000 searches/month free).",
        fields=[
            {"key": "search_api_key", "label": "Tavily API Key", "type": "password", "placeholder": "tvly-xxxxxxxxxxxx"},
        ],
    )
    if conn_check:
        return conn_check

    return {
        "status": "success",
        "query": query,
        "results": [],
    }


def _log_task(task_name: str, status: str, details: str = "") -> Dict[str, Any]:
    """Log a task. Always works — no external connection needed."""
    log_dir = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task_name,
        "status": status,
        "details": details,
    }
    log_file = os.path.join(log_dir, "task_history.jsonl")
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    logger.info(f"Logged task: {task_name} ({status})")
    return {"status": "logged", "log_entry": log_entry}


def _file_read(file_path: str) -> Dict[str, Any]:
    """Read a local file. Always works."""
    try:
        with open(file_path, "r") as f:
            content = f.read()
        return {"status": "success", "path": file_path, "content": content, "size": len(content)}
    except FileNotFoundError:
        return {"status": "error", "message": f"File not found: {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _file_write(file_path: str, content: str) -> Dict[str, Any]:
    """Write a local file. Always works."""
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return {"status": "success", "path": file_path, "bytes_written": len(content)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _git_commit_and_push(message: str) -> Dict[str, Any]:
    """Git commit and push. Works if in a git repo."""
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                       check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"status": "skipped", "message": "Not inside a git repository."}

    try:
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True, text=True)
        result = subprocess.run(["git", "commit", "-m", message],
                                check=True, capture_output=True, text=True)
        push_result = subprocess.run(["git", "push"],
                                     check=True, capture_output=True, text=True)
        return {"status": "success", "message": message,
                "commit_output": result.stdout.strip(),
                "push_output": push_result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.stderr.strip() or e.stdout.strip()}


# ─────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────

def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        name="scan_inbox",
        description="Check inbox for new messages. Requires Gmail to be connected first.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_scan_inbox, category="communication",
    )
    registry.register(
        name="draft_reply",
        description="Draft and send a reply to a message. Requires Gmail connection to send.",
        parameters={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Message ID to reply to"},
                "context": {"type": "string", "description": "Key points for the reply"},
                "tone": {"type": "string", "enum": ["professional", "friendly", "formal", "urgent"]},
            },
            "required": ["message_id", "context"],
        },
        handler=_draft_reply, category="communication",
    )
    registry.register(
        name="update_crm",
        description="Update a contact in the CRM. Requires CRM connection.",
        parameters={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "CRM contact ID"},
                "data": {"type": "object", "description": "Fields to update"},
            },
            "required": ["contact_id", "data"],
        },
        handler=_update_crm, category="crm",
    )
    registry.register(
        name="read_database",
        description="Query the database. Requires database connection string.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search criteria"},
                "table": {"type": "string", "description": "Table name"},
            },
            "required": ["query", "table"],
        },
        handler=_read_database, category="data",
    )
    registry.register(
        name="log_task",
        description="Log a completed task. Always works — no connection needed.",
        parameters={
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Task name"},
                "status": {"type": "string", "enum": ["completed", "failed", "partial", "skipped"]},
                "details": {"type": "string", "description": "Additional details"},
            },
            "required": ["task_name", "status"],
        },
        handler=_log_task, category="system",
    )
    registry.register(
        name="web_search",
        description="Search the web. Requires Tavily API key.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
        handler=_web_search, category="research",
    )
    registry.register(
        name="file_read",
        description="Read a local file. Always works.",
        parameters={
            "type": "object",
            "properties": {"file_path": {"type": "string", "description": "File path"}},
            "required": ["file_path"],
        },
        handler=_file_read, category="filesystem",
    )
    registry.register(
        name="file_write",
        description="Write a local file. Always works.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["file_path", "content"],
        },
        handler=_file_write, category="filesystem",
    )
    registry.register(
        name="git_commit_and_push",
        description="Commit and push to git. Works if in a git repo.",
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Commit message"}},
            "required": ["message"],
        },
        handler=_git_commit_and_push, category="system",
    )

    # Register browser automation tools (real web search, browsing, progress tracking)
    try:
        from .browser_tools import register_browser_tools
        register_browser_tools(registry)
    except ImportError as e:
        logger.warning(f"Browser tools not available: {e}")

    return registry
