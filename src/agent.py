"""
Core ReAct (Reasoning + Acting) Agent.
Implements the continuous thought → decision → action → observation loop.
Includes an event callback system for real-time dashboard streaming.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable

from .config import AppConfig
from .models import ModelRouter
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# System Prompt — focused on BEHAVIOR, not tool listing
# (tools are described via function-calling schema)
# ─────────────────────────────────────────────

REACT_SYSTEM_PROMPT = """You are an autonomous cloud workforce agent operating on the ReAct framework.

## Your Operating Loop
Follow this strict 4-step cycle each iteration:

1. **THOUGHT**: Analyze the current situation. What do you know? What do you need next?
2. **DECISION**: Select the best tool and explain why.
3. **ACTION**: Call the tool using function calling.
4. **OBSERVATION**: Read the result. Succeed → plan next step. Fail → diagnose and adapt.

## Rules
- You are autonomous. Never ask for human input — make decisions yourself.
- Always call `log_task` after completing a significant action.
- If a tool fails, try a different approach. Never repeat an identical failed action.
- Be efficient. Do not re-execute actions that already succeeded.
- When the goal is fully accomplished, respond with "TASK_COMPLETE" and a summary.
- Keep thinking concise but thorough.

## Current Goal
{goal}

Begin working on the goal now. Start with your THOUGHT about what to do first.
"""


class ReActAgent:
    """
    The core autonomous agent implementing the ReAct loop.

    Lifecycle:
        1. Wakes up with a goal
        2. Enters the ReAct loop (Thought → Decision → Action → Observation)
        3. Uses tools to interact with the environment
        4. Self-corrects on errors
        5. Exits when goal is accomplished or max iterations reached
    """

    def __init__(self, config: AppConfig, tools: ToolRegistry,
                 event_callback: Optional[Callable[[str, Dict], None]] = None):
        self.config = config
        self.tools = tools
        self.router = ModelRouter(config)
        self.conversation_history: List[Dict[str, Any]] = []
        self.iteration_count = 0
        self.task_summary = ""
        self.start_time: Optional[float] = None
        self.event_callback = event_callback
        self._agent_id = str(uuid.uuid4())[:8]

    def _emit(self, event_type: str, data: Dict[str, Any]):
        """Emit a real-time event for the dashboard."""
        payload = {
            "agent_id": self._agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iteration": self.iteration_count,
            **data,
        }
        logger.debug(f"EVENT [{event_type}]: {json.dumps(payload, default=str)[:200]}")
        if self.event_callback:
            try:
                self.event_callback(event_type, payload)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

    def run(self, goal: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point. Runs the ReAct loop until the goal is accomplished
        or the maximum number of iterations is reached.
        """
        self.start_time = time.time()
        goal = goal or self.config.agent_goal
        logger.info(f"🚀 Agent waking up with goal: {goal}")
        self._emit("agent_start", {"goal": goal})

        # Build the system prompt (no redundant tool listing — function calling handles that)
        system_prompt = REACT_SYSTEM_PROMPT.format(goal=goal)

        # Initialize conversation
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Begin working on this goal now: {goal}"},
        ]

        # Main ReAct loop
        while self.iteration_count < self.config.max_react_iterations:
            self.iteration_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"🔄 ITERATION {self.iteration_count}/{self.config.max_react_iterations}")
            logger.info(f"{'='*60}")
            self._emit("iteration_start", {
                "iteration": self.iteration_count,
                "max_iterations": self.config.max_react_iterations,
            })

            try:
                # Step 1-2: THINK + DECIDE
                response = self._think_and_decide()

                if "tool_calls" in response and response["tool_calls"]:
                    # Step 3: EXECUTE tools
                    tool_results = self._execute_tools(response["tool_calls"])

                    # Step 4: OBSERVE — feed results back into conversation
                    self._observe(response, tool_results)

                    # Check for completion
                    if self._check_completion(response, tool_results):
                        self._emit("agent_complete", {"summary": self.task_summary})
                        break
                else:
                    # Agent responded without tool calls
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": response.get("content", ""),
                    })
                    self._emit("agent_text", {
                        "content": response.get("content", ""),
                        "type": "assistant_message",
                    })

                    if "TASK_COMPLETE" in (response.get("content") or ""):
                        self.task_summary = response["content"]
                        self._emit("agent_complete", {"summary": self.task_summary})
                        logger.info("✅ Agent reports task completion!")
                        break

                    # Nudge to take action
                    self.conversation_history.append({
                        "role": "user",
                        "content": (
                            "Continue working on the goal. Use the available tools to make progress. "
                            "If the task is complete, respond with TASK_COMPLETE and a summary."
                        ),
                    })

            except Exception as e:
                logger.error(f"Iteration {self.iteration_count} failed: {e}")
                self._emit("iteration_error", {"error": str(e)})
                # Self-correction: add the error to conversation and try again
                self.conversation_history.append({
                    "role": "assistant",
                    "content": f"Error encountered: {str(e)}",
                })
                self.conversation_history.append({
                    "role": "user",
                    "content": (
                        f"The previous step failed with error: {str(e)}. "
                        "Diagnose the issue, try a different approach, and continue working toward the goal."
                    ),
                })

        # Final report
        elapsed = time.time() - (self.start_time or time.time())
        report = self._generate_report(goal, elapsed)
        self._emit("report", report)
        return report

    def send_message(self, message: str) -> str:
        """
        Send a chat message to the agent (used by the dashboard for interactive mode).
        Returns the agent's response text.
        """
        self._emit("user_message", {"content": message})

        self.conversation_history.append({
            "role": "user",
            "content": message,
        })

        try:
            response = self.router.query(
                role="task_manager",
                messages=self.conversation_history,
                tools=self.tools.get_tools_schema() or None,
                fallback_role="data_reader",
            )
        except Exception as e:
            error_msg = f"I encountered an error processing your message: {e}"
            self._emit("agent_error", {"error": str(e)})
            return error_msg

        # If the model wants to call tools, execute them
        if response.get("tool_calls"):
            tool_results = self._execute_tools(response["tool_calls"])
            self._observe(response, tool_results)

            # Get a follow-up response after tool results
            follow_up = self.router.query(
                role="task_manager",
                messages=self.conversation_history,
                fallback_role="data_reader",
            )
            content = follow_up.get("content", "")
        else:
            content = response.get("content", "")

        self.conversation_history.append({
            "role": "assistant",
            "content": content,
        })
        self._emit("agent_text", {"content": content, "type": "chat_response"})
        return content

    def _think_and_decide(self) -> Dict[str, Any]:
        """Phase 1-2 of the ReAct loop: Analyze + Choose."""
        logger.info("🧠 THINKING + DECIDING...")
        self._emit("thinking", {"phase": "think_and_decide"})

        tools_schema = self.tools.get_tools_schema()
        response = self.router.query(
            role="task_manager",
            messages=self.conversation_history,
            tools=tools_schema if tools_schema else None,
            fallback_role="data_reader",
        )

        content_preview = (response.get("content") or "")[:300]
        logger.info(f"💭 Model response: {content_preview}...")
        self._emit("model_response", {
            "content": response.get("content", ""),
            "has_tool_calls": bool(response.get("tool_calls")),
            "model_role": "task_manager",
        })

        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                logger.info(f"🔧 Action chosen: {tc['function']}")
                self._emit("tool_decision", {
                    "tool_name": tc["function"],
                    "arguments": tc.get("arguments", "{}"),
                })

        return response

    def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        """Phase 3: Execute the chosen tool(s)."""
        results = []
        for tc in tool_calls:
            tool_name = tc["function"]
            try:
                arguments = json.loads(tc["arguments"]) if tc.get("arguments") else {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse arguments for {tool_name}: {e}")
                arguments = {}
                self._emit("tool_parse_error", {
                    "tool_name": tool_name,
                    "raw_arguments": tc.get("arguments", ""),
                    "error": str(e),
                })

            logger.info(f"⚡ EXECUTING: {tool_name}({json.dumps(arguments)[:100]})")
            self._emit("tool_executing", {
                "tool_name": tool_name,
                "arguments": arguments,
            })

            start = time.time()
            result = self.tools.execute(tool_name, arguments)
            elapsed = time.time() - start

            results.append({
                "tool_call_id": tc.get("id", ""),
                "tool_name": tool_name,
                "result": result,
            })

            logger.info(f"📋 RESULT ({elapsed:.2f}s): {result[:200] if isinstance(result, str) else json.dumps(result)[:200]}")
            self._emit("tool_result", {
                "tool_name": tool_name,
                "result": result[:500] if isinstance(result, str) else json.dumps(result)[:500],
                "elapsed_seconds": round(elapsed, 3),
            })

            # CHECK: Did the tool return needs_connection?
            try:
                result_data = json.loads(result) if isinstance(result, str) else result
                if isinstance(result_data, dict) and result_data.get("status") == "needs_connection":
                    self._emit("connection_needed", {
                        "tool": result_data.get("tool", tool_name),
                        "display_name": result_data.get("display_name", tool_name),
                        "message": result_data.get("message", "Connection required."),
                        "get_link": result_data.get("get_link", ""),
                        "get_instructions": result_data.get("get_instructions", ""),
                        "required_fields": result_data.get("required_fields", []),
                    })
            except (json.JSONDecodeError, TypeError):
                pass

        return results

    def _observe(self, assistant_response: Dict, tool_results: List[Dict]):
        """
        Phase 4: Feed observations back into conversation.
        FIX: Now properly includes tool_calls in the assistant message.
        """
        logger.info("👁️ OBSERVING results...")

        # FIX: Include tool_calls in the assistant message so the API knows
        # which tool calls the model made. Without this, the 'tool' role
        # messages with tool_call_id won't match anything.
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": assistant_response.get("content") or "",
        }
        if assistant_response.get("tool_calls"):
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in assistant_response["tool_calls"]
            ]
        self.conversation_history.append(assistant_msg)

        # Add each tool result
        for tr in tool_results:
            self.conversation_history.append({
                "role": "tool",
                "tool_call_id": tr.get("tool_call_id", ""),
                "content": tr["result"] if isinstance(tr["result"], str) else json.dumps(tr["result"]),
            })

        self._emit("observation", {
            "num_tool_results": len(tool_results),
            "conversation_length": len(self.conversation_history),
        })

    def _check_completion(self, response: Dict, tool_results: List[Dict]) -> bool:
        """Check if any content indicates task completion."""
        content = response.get("content") or ""
        if "TASK_COMPLETE" in content:
            self.task_summary = content
            return True

        for tr in tool_results:
            result_str = tr["result"] if isinstance(tr["result"], str) else json.dumps(tr["result"])
            if "TASK_COMPLETE" in result_str:
                self.task_summary = result_str
                return True

        return False

    def _generate_report(self, goal: str, elapsed: float) -> Dict[str, Any]:
        """Generate a final execution report."""
        report = {
            "goal": goal,
            "iterations": self.iteration_count,
            "elapsed_seconds": round(elapsed, 2),
            "completed": "TASK_COMPLETE" in (self.task_summary or ""),
            "summary": self.task_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conversation_turns": len(self.conversation_history),
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"📊 EXECUTION REPORT")
        logger.info(f"{'='*60}")
        logger.info(f"  Goal: {goal}")
        logger.info(f"  Iterations: {self.iteration_count}")
        logger.info(f"  Duration: {elapsed:.2f}s")
        logger.info(f"  Completed: {report['completed']}")
        logger.info(f"{'='*60}")

        # Save report to logs
        self.tools.execute("log_task", {
            "task_name": "agent_execution",
            "status": "completed" if report["completed"] else "partial",
            "details": json.dumps(report, default=str),
        })

        return report
