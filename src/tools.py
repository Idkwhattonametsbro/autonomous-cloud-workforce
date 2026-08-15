"""
Tool definitions for the Autonomous Cloud Workforce agent.
Each tool is a self-contained function with metadata for the LLM to understand and call.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger(__name__)

# Resolve the project root once — works regardless of cwd or how the script was invoked
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────

class ToolRegistry:
    """Manages the collection of tools available to the agent."""

    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._handlers: Dict[str, Callable] = {}
        self._categories: Dict[str, str] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict,
        handler: Callable,
        category: str = "general",
    ):
        """Register a new tool with its metadata and handler function."""
        self._tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._handlers[name] = handler
        self._categories[name] = category
        logger.debug(f"Registered tool: {name} (category: {category})")

    def get_tools_schema(self) -> List[Dict]:
        """Return all tool schemas in OpenAI function-calling format."""
        return list(self._tools.values())

    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments."""
        if name not in self._handlers:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = self._handlers[name](**arguments)
            return json.dumps(result, default=str)
        except TypeError as e:
            # Likely bad argument types — surface clearly
            logger.error(f"Tool '{name}' argument error: {e}")
            return json.dumps({"error": f"Invalid arguments for {name}: {e}"})
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return json.dumps({"error": str(e)})

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> Optional[Dict]:
        """Get a tool's schema and category."""
        if name not in self._tools:
            return None
        return {
            "schema": self._tools[name],
            "category": self._categories.get(name, "general"),
        }


# ─────────────────────────────────────────────
# Built-in Tool Implementations
# ─────────────────────────────────────────────

def _scan_inbox() -> Dict[str, Any]:
    """
    Simulates scanning a business inbox for new messages.
    In production, connect to Gmail API, Outlook, or your email provider.
    """
    logger.info("Scanning inbox for new messages...")
    # --- INTEGRATION POINT ---
    # from google.oauth2.credentials import Credentials
    # from googleapiclient.discovery import build
    # ...
    return {
        "status": "success",
        "new_messages": 0,
        "messages": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _draft_reply(message_id: str, context: str, tone: str = "professional") -> Dict[str, Any]:
    """
    Drafts a reply to a message. The actual content generation is delegated
    to the agent's LLM — this tool provides the structural framework.
    """
    logger.info(f"Drafting reply to message {message_id} (tone: {tone})")
    return {
        "status": "success",
        "message_id": message_id,
        "draft": (
            f"[AI-generated reply to message {message_id} with {tone} tone, "
            f"incorporating context: {context[:100]}...]"
        ),
        "drafted_at": datetime.now(timezone.utc).isoformat(),
    }


def _update_crm(contact_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Updates a CRM record. In production, connect to HubSpot, Salesforce, etc.
    """
    logger.info(f"Updating CRM record for contact {contact_id}")
    # --- INTEGRATION POINT ---
    return {
        "status": "success",
        "contact_id": contact_id,
        "updated_fields": list(data.keys()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_database(query: str, table: str) -> Dict[str, Any]:
    """
    Reads from a database. In production, connect to your actual database.
    """
    logger.info(f"Querying table '{table}': {query}")
    # --- INTEGRATION POINT ---
    return {
        "status": "success",
        "table": table,
        "rows": [],
        "row_count": 0,
        "query": query,
    }


def _log_task(task_name: str, status: str, details: str = "") -> Dict[str, Any]:
    """
    Logs a completed task to the agent's task history file.
    Uses _PROJECT_ROOT so it works regardless of cwd.
    """
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


def _web_search(query: str) -> Dict[str, Any]:
    """
    Performs a web search. In production, connect to SerpAPI, Tavily, or similar.
    """
    logger.info(f"Web search: {query}")
    # --- INTEGRATION POINT ---
    return {
        "status": "success",
        "query": query,
        "results": [],
        "note": "Web search tool requires API integration (SerpAPI, Tavily, etc.)",
    }


def _file_read(file_path: str) -> Dict[str, Any]:
    """Reads a file from the workspace."""
    try:
        with open(file_path, "r") as f:
            content = f.read()
        return {"status": "success", "path": file_path, "content": content, "size": len(content)}
    except FileNotFoundError:
        return {"status": "error", "message": f"File not found: {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _file_write(file_path: str, content: str) -> Dict[str, Any]:
    """Writes content to a file in the workspace."""
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
    """
    Commits and pushes changes to the Git repository.
    Gracefully handles non-git environments.
    """
    # Check if we're inside a git repo first
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True, capture_output=True, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"status": "skipped", "message": "Not inside a git repository — skipping commit."}

    try:
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True, text=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            check=True, capture_output=True, text=True,
        )
        push_result = subprocess.run(
            ["git", "push"],
            check=True, capture_output=True, text=True,
        )
        return {
            "status": "success",
            "message": message,
            "commit_output": result.stdout.strip(),
            "push_output": push_result.stdout.strip(),
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": e.stderr.strip() or e.stdout.strip(),
        }


# ─────────────────────────────────────────────
# Tool Registration Factory
# ─────────────────────────────────────────────

def create_default_registry() -> ToolRegistry:
    """Create a ToolRegistry with all default tools registered."""
    registry = ToolRegistry()

    registry.register(
        name="scan_inbox",
        description="Check for new client inquiries or messages in the business inbox. "
                    "Returns a list of unread messages with their IDs and summaries.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_scan_inbox,
        category="communication",
    )

    registry.register(
        name="draft_reply",
        description="Draft a professional reply to a specific message. "
                    "Requires the message ID and context about what to include.",
        parameters={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The ID of the message to reply to"},
                "context": {"type": "string", "description": "Key points to include in the reply"},
                "tone": {
                    "type": "string",
                    "enum": ["professional", "friendly", "formal", "urgent"],
                    "description": "The tone of the reply",
                },
            },
            "required": ["message_id", "context"],
        },
        handler=_draft_reply,
        category="communication",
    )

    registry.register(
        name="update_crm",
        description="Update a contact record in the CRM system. "
                    "Use this to log interactions, update statuses, or add notes.",
        parameters={
            "type": "object",
            "properties": {
                "contact_id": {"type": "string", "description": "The CRM contact ID"},
                "data": {
                    "type": "object",
                    "description": "Key-value pairs of fields to update",
                },
            },
            "required": ["contact_id", "data"],
        },
        handler=_update_crm,
        category="crm",
    )

    registry.register(
        name="read_database",
        description="Query the business database for information. "
                    "Returns matching rows from the specified table.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query or search criteria"},
                "table": {"type": "string", "description": "The database table to query"},
            },
            "required": ["query", "table"],
        },
        handler=_read_database,
        category="data",
    )

    registry.register(
        name="log_task",
        description="Log a completed task to the agent's persistent history. "
                    "Always call this after completing a significant action.",
        parameters={
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Name of the completed task"},
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "partial", "skipped"],
                    "description": "Outcome status",
                },
                "details": {"type": "string", "description": "Additional details about the task"},
            },
            "required": ["task_name", "status"],
        },
        handler=_log_task,
        category="system",
    )

    registry.register(
        name="web_search",
        description="Search the web for current information. "
                    "Useful for research, fact-checking, or finding resources.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
        handler=_web_search,
        category="research",
    )

    registry.register(
        name="file_read",
        description="Read a file from the workspace by its path.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to read"},
            },
            "required": ["file_path"],
        },
        handler=_file_read,
        category="filesystem",
    )

    registry.register(
        name="file_write",
        description="Write content to a file in the workspace. Creates parent directories as needed.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to write the file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["file_path", "content"],
        },
        handler=_file_write,
        category="filesystem",
    )

    registry.register(
        name="git_commit_and_push",
        description="Stage all changes, commit with a message, and push to the remote repository.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message describing the changes"},
            },
            "required": ["message"],
        },
        handler=_git_commit_and_push,
        category="system",
    )

    return registry
