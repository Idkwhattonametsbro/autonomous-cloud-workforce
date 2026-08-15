"""
Model routing module.
Handles communication with Groq and OpenRouter APIs based on task requirements.
"""

import json
import logging
import time
from typing import Optional, List, Dict, Any

import requests
from groq import Groq

from .config import AppConfig, ModelConfig

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes tasks to the appropriate LLM based on the model strategy."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.groq_client = Groq(api_key=config.groq_api_key, timeout=60)
        self._openrouter_session = requests.Session()
        self._openrouter_session.headers.update({
            "Authorization": f"Bearer {config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/autonomous-cloud-workforce",
            "X-Title": "Autonomous Cloud Workforce Agent",
        })

    def query(
        self,
        role: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        fallback_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a query to the model assigned to the given role.
        Returns the model's response as a dict with 'content' and optional 'tool_calls'.
        """
        model_config = self.config.get_model(role)
        try:
            if model_config.provider == "groq":
                return self._query_groq(model_config, messages, tools)
            else:
                return self._query_openrouter(model_config, messages, tools)
        except Exception as e:
            logger.error(f"Model query failed for role '{role}': {e}")
            if fallback_role and fallback_role != role:
                logger.info(f"Falling back to model role: {fallback_role}")
                return self.query(fallback_role, messages, tools)
            raise

    def _query_groq(
        self, model: ModelConfig, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Query a model hosted on Groq (Llama 3.3 70B)."""
        kwargs: Dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.groq_client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        result: Dict[str, Any] = {"content": choice.content or ""}
        if hasattr(choice, "tool_calls") and choice.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.tool_calls
            ]
        return result

    def _query_openrouter(
        self, model: ModelConfig, messages: List[Dict], tools: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Query a model hosted on OpenRouter (Gemini, Qwen, etc.)."""
        payload: Dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "max_tokens": model.max_tokens,
            "temperature": model.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = self._openrouter_session.post(
            f"{self.config.openrouter_base_url}/chat/completions",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]

        result: Dict[str, Any] = {"content": choice.get("content") or ""}
        if choice.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "function": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                }
                for tc in choice["tool_calls"]
            ]
        return result

    def classify_task(self, task_description: str) -> str:
        """
        Use the primary task manager to classify which model role
        should handle a given sub-task.
        """
        system_prompt = (
            "You are a task router. Given a sub-task description, classify it into one of "
            "these roles by responding with ONLY the role name:\n"
            "- task_manager: General reasoning, planning, email drafting, decision making\n"
            "- data_reader: Reading large documents, analyzing long text, processing datasets\n"
            "- code_specialist: Writing code, modifying files, mathematical computations\n\n"
            "Respond with only one word: the role name."
        )
        response = self.query("task_manager", [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Classify this task: {task_description}"},
        ])
        role = (response.get("content") or "").strip().lower()
        valid_roles = ["task_manager", "data_reader", "code_specialist"]
        return role if role in valid_roles else "task_manager"
