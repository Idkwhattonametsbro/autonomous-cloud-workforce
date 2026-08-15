"""
Self-Improvement Engine
The agent analyzes its own performance after each run, learns from mistakes,
and evolves its strategies over time. All learnings persist in the memory store.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SelfImprover:
    """Analyzes agent runs and evolves strategies."""

    def __init__(self, memory_store):
        self.memory = memory_store

    def analyze_run(self, report: Dict, events: List[Dict]) -> Dict[str, Any]:
        """
        Post-run analysis: what worked, what failed, what to improve.
        Returns improvement actions to store in memory.
        """
        analysis = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": report.get("goal", ""),
            "iterations": report.get("iterations", 0),
            "completed": report.get("completed", False),
            "duration": report.get("elapsed_seconds", 0),
            "findings": [],
            "improvements": [],
        }

        # 1. Analyze tool usage patterns
        tool_counts = {}
        tool_errors = {}
        for evt in events:
            data = evt.get("data", {})
            etype = evt.get("event_type", "")
            if etype == "tool_executing":
                name = data.get("tool_name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1
            elif etype == "tool_result":
                result_str = data.get("result", "")
                name = data.get("tool_name", "")
                if '"error"' in result_str or '"status": "error"' in result_str:
                    tool_errors[name] = tool_errors.get(name, 0) + 1
            elif etype == "iteration_error":
                analysis["findings"].append(f"Error in iteration: {data.get('error', 'unknown')}")

        # 2. Efficiency analysis
        if report.get("iterations", 0) > 0:
            avg_time_per_iter = report["elapsed_seconds"] / report["iterations"]
            if avg_time_per_iter > 5:
                analysis["findings"].append(f"Slow iterations: {avg_time_per_iter:.1f}s average. Consider reducing tool calls.")
                analysis["improvements"].append("reduce_tool_calls")
            if avg_time_per_iter < 1:
                analysis["findings"].append(f"Fast iterations: {avg_time_per_iter:.1f}s average. Good efficiency.")

        # 3. Tool effectiveness
        for tool, errors in tool_errors.items():
            total = tool_counts.get(tool, 0)
            if total > 0 and errors / total > 0.3:
                analysis["findings"].append(f"Tool '{tool}' has {errors}/{total} failure rate. Consider alternative approach.")
                analysis["improvements"].append(f"avoid_{tool}")

        # 4. Completion analysis
        if not report.get("completed"):
            analysis["findings"].append("Task did not complete within iteration limit. Goal may be too broad.")
            analysis["improvements"].append("break_down_goals")
        else:
            analysis["findings"].append("Task completed successfully.")

        # 5. Store learnings
        strategy = self._derive_strategy(analysis)
        self.memory.remember(
            "last_strategy", json.dumps(strategy), "self_improvement",
            source="self_analysis", confidence=0.9
        )

        # Track run history for trend analysis
        history = self.memory.recall("run_history", "self_improvement")
        run_history = json.loads(history) if history else []
        run_history.append({
            "completed": report.get("completed", False),
            "iterations": report.get("iterations", 0),
            "duration": report.get("elapsed_seconds", 0),
            "tool_counts": tool_counts,
            "tool_errors": tool_errors,
        })
        # Keep last 50 runs
        run_history = run_history[-50:]
        self.memory.remember(
            "run_history", json.dumps(run_history), "self_improvement",
            source="self_analysis", confidence=1.0
        )

        # Update success rate
        total = len(run_history)
        successes = sum(1 for r in run_history if r.get("completed"))
        self.memory.remember(
            "success_rate", f"{successes}/{total} ({successes/total*100:.0f}%)" if total > 0 else "N/A",
            "self_improvement", source="self_analysis"
        )

        analysis["strategy"] = strategy
        return analysis

    def _derive_strategy(self, analysis: Dict) -> Dict[str, Any]:
        """Derive an actionable strategy from the analysis."""
        strategy = {
            "preferred_tool_order": [],
            "avoid_tools": [],
            "max_recommended_iterations": 10,
            "notes": [],
        }

        for improvement in analysis.get("improvements", []):
            if improvement.startswith("avoid_"):
                tool = improvement.replace("avoid_", "")
                strategy["avoid_tools"].append(tool)
                strategy["notes"].append(f"Avoid using {tool} — high failure rate detected.")
            elif improvement == "reduce_tool_calls":
                strategy["notes"].append("Batch operations where possible to reduce iteration count.")
            elif improvement == "break_down_goals":
                strategy["notes"].append("Break complex goals into sub-goals. Ask user for clarification if goal is ambiguous.")

        # If most runs succeed, keep strategy simple
        history_str = self.memory.recall("run_history", "self_improvement")
        if history_str:
            history = json.loads(history_str)
            recent = history[-5:]
            if all(r.get("completed") for r in recent):
                strategy["notes"].append("Last 5 runs all succeeded. Current strategy is working well.")

        return strategy

    def get_current_strategy(self) -> Dict[str, Any]:
        """Retrieve the latest strategy."""
        strategy_str = self.memory.recall("last_strategy", "self_improvement")
        if strategy_str:
            return json.loads(strategy_str)
        return {
            "preferred_tool_order": [],
            "avoid_tools": [],
            "max_recommended_iterations": 10,
            "notes": ["No strategy yet. Will learn from first run."],
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a human-readable performance summary."""
        history_str = self.memory.recall("run_history", "self_improvement")
        success = self.memory.recall("success_rate", "self_improvement")
        strategy = self.get_current_strategy()

        if not history_str:
            return {"message": "No runs recorded yet."}

        history = json.loads(history_str)
        total = len(history)
        completed = sum(1 for r in history if r.get("completed"))
        avg_iter = sum(r.get("iterations", 0) for r in history) / total if total else 0
        avg_dur = sum(r.get("duration", 0) for r in history) / total if total else 0

        # All tools ever used
        all_tools = {}
        for run in history:
            for tool, count in run.get("tool_counts", {}).items():
                all_tools[tool] = all_tools.get(tool, 0) + count

        return {
            "total_runs": total,
            "success_rate": f"{completed}/{total} ({completed/total*100:.0f}%)" if total > 0 else "N/A",
            "avg_iterations": round(avg_iter, 1),
            "avg_duration": f"{avg_dur:.1f}s",
            "tools_used": all_tools,
            "current_strategy_notes": strategy.get("notes", []),
            "evolution_stage": self._get_evolution_stage(total, completed),
        }

    def _get_evolution_stage(self, total_runs: int, successes: int) -> str:
        """Determine how evolved the agent is."""
        if total_runs == 0:
            return "Stage 0: Initial — No runs yet"
        elif total_runs < 3:
            return "Stage 1: Learning — Gathering data from first runs"
        elif total_runs < 10:
            rate = successes / total_runs
            if rate > 0.8:
                return "Stage 2: Adapting — Forming reliable strategies"
            return "Stage 2: Experimenting — Testing different approaches"
        elif total_runs < 30:
            return "Stage 3: Optimizing — Refining tool selection and efficiency"
        else:
            return "Stage 4: Autonomous — Self-tuned and highly reliable"


# ═══════════════════════════════════════════════════
# TASK PLANNER — Detects missing info and requests it
# ═══════════════════════════════════════════════════

class TaskPlanner:
    """
    Analyzes a user's task request. Determines:
    - Can it be executed immediately?
    - What information is missing?
    - What credentials/access are needed?
    Then generates info-request prompts for the user.
    """

    # Known task patterns and their required info
    TASK_PATTERNS = {
        "email_send": {
            "keywords": ["send email", "send mail", "email to", "mail to", "gmail"],
            "required_info": [
                {"key": "gmail_address", "label": "Your Gmail Address", "type": "email", "placeholder": "you@gmail.com"},
                {"key": "gmail_app_password", "label": "Gmail App Password", "type": "password", "placeholder": "xxxx-xxxx-xxxx-xxxx",
                 "help": "Generate at myaccount.google.com > Security > App Passwords"},
            ],
            "dynamic_info": [
                {"key": "recipient_list", "label": "Recipient Emails", "type": "textarea", "placeholder": "one@email.com\ntwo@email.com",
                 "help": "One email per line"},
            ],
            "security_note": "Your credentials are stored locally in encrypted form and never leave this server. They are only used to authenticate with Gmail's API on your behalf.",
        },
        "paypal_request": {
            "keywords": ["paypal", "payment", "money", "donation", "request money"],
            "required_info": [
                {"key": "paypal_address", "label": "Your PayPal Email/Link", "type": "text", "placeholder": "you@paypal.com or paypal.me/yourname"},
            ],
            "dynamic_info": [],
            "security_note": "Your PayPal information is stored locally and encrypted. It is only used to construct payment links in outgoing messages. No financial transactions are initiated automatically.",
        },
        "crm_update": {
            "keywords": ["crm", "hubspot", "salesforce", "contacts", "pipeline"],
            "required_info": [
                {"key": "crm_api_key", "label": "CRM API Key", "type": "password", "placeholder": "your-api-key"},
                {"key": "crm_platform", "label": "CRM Platform", "type": "select", "options": ["HubSpot", "Salesforce", "Pipedrive", "Other"]},
            ],
            "dynamic_info": [],
            "security_note": "Your API key is stored encrypted locally and used only to authenticate with your CRM provider's API.",
        },
        "database_query": {
            "keywords": ["database", "sql", "query", "postgres", "mysql", "sqlite"],
            "required_info": [
                {"key": "db_connection", "label": "Database Connection String", "type": "password", "placeholder": "postgresql://user:pass@host:5432/db"},
            ],
            "dynamic_info": [],
            "security_note": "Your database credentials are stored encrypted locally and only used to establish read connections. No write operations are performed without explicit confirmation.",
        },
        "github_action": {
            "keywords": ["github", "repo", "commit", "push", "pull request"],
            "required_info": [
                {"key": "github_token", "label": "GitHub Personal Access Token", "type": "password", "placeholder": "ghp_xxxxxxxxxxxx"},
                {"key": "github_repo", "label": "Repository", "type": "text", "placeholder": "username/repo-name"},
            ],
            "dynamic_info": [],
            "security_note": "Your GitHub token is stored encrypted and used only for repository operations you explicitly request. It has the minimum permissions needed.",
        },
        "general": {
            "keywords": [],
            "required_info": [],
            "dynamic_info": [],
            "security_note": "",
        },
    }

    def analyze_task(self, task_description: str) -> Dict[str, Any]:
        """
        Analyze a task and determine what info is needed.
        Returns either:
          - {"status": "ready", "plan": ...} if all info is available
          - {"status": "needs_info", "requests": [...], "pattern": ...} if info is missing
        """
        # Match against known patterns
        matched_pattern = None
        task_lower = task_description.lower()

        for pattern_key, pattern in self.TASK_PATTERNS.items():
            if pattern_key == "general":
                continue
            if any(kw in task_lower for kw in pattern["keywords"]):
                matched_pattern = pattern_key
                break

        if not matched_pattern:
            # No specific pattern — try to execute directly
            return {
                "status": "ready",
                "plan": {
                    "goal": task_description,
                    "approach": "general",
                    "tools": ["scan_inbox", "log_task"],
                },
            }

        pattern = self.TASK_PATTERNS[matched_pattern]

        # Check what info we already have in memory
        missing_info = []
        for req in pattern["required_info"]:
            stored = self._check_stored_info(req["key"])
            if not stored:
                missing_info.append(req)

        if missing_info:
            return {
                "status": "needs_info",
                "pattern": matched_pattern,
                "requests": missing_info,
                "security_note": pattern.get("security_note", ""),
                "task_description": task_description,
            }

        # All required info is available
        return {
            "status": "ready",
            "plan": {
                "goal": task_description,
                "approach": matched_pattern,
                "tools": self._get_tools_for_pattern(matched_pattern),
            },
        }

    def _check_stored_info(self, key: str) -> bool:
        """Check if we have this info stored in memory."""
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        val = mem.recall(key, "user_credentials")
        return val is not None

    def _get_tools_for_pattern(self, pattern: str) -> List[str]:
        tool_map = {
            "email_send": ["scan_inbox", "draft_reply", "log_task"],
            "paypal_request": ["draft_reply", "log_task"],
            "crm_update": ["update_crm", "log_task"],
            "database_query": ["read_database", "log_task"],
            "github_action": ["file_read", "git_commit_and_push", "log_task"],
        }
        return tool_map.get(pattern, ["log_task"])
