"""
Configuration module for the Autonomous Cloud Workforce.
Manages API keys and model routing settings via environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ModelConfig:
    """Configuration for a single model endpoint."""
    name: str
    provider: str  # "groq" or "openrouter"
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.1
    description: str = ""


@dataclass
class AppConfig:
    """Application-wide configuration."""
    # API Keys
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # API Endpoints
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Agent Settings
    max_react_iterations: int = 15
    agent_goal: str = ""
    verbose: bool = True

    # Model Registry
    models: Dict[str, ModelConfig] = field(default_factory=dict)

    def __post_init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", self.groq_api_key)
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", self.openrouter_api_key)
        self.agent_goal = os.getenv(
            "AGENT_GOAL",
            "Check for new client inquiries, draft professional responses, "
            "and log all completed tasks."
        )
        self.verbose = os.getenv("VERBOSE", "true").lower() == "true"

        # Register default models
        self.models = {
            "task_manager": ModelConfig(
                name="Llama 3.3 70B (Task Manager)",
                provider="groq",
                model_id="llama-3.3-70b-versatile",
                max_tokens=8192,
                temperature=0.1,
                description="Primary executive brain. Elite logic and structured function calling.",
            ),
            "data_reader": ModelConfig(
                name="Gemini 2.5 Flash (Data Reader)",
                provider="openrouter",
                model_id="google/gemini-2.5-flash",
                max_tokens=65536,
                temperature=0.1,
                description="Massive context window for reading large documents and datasets.",
            ),
            "code_specialist": ModelConfig(
                name="Qwen 2.5 Coder 32B (Code Specialist)",
                provider="openrouter",
                model_id="qwen/qwen-2.5-coder-32b-instruct",
                max_tokens=16384,
                temperature=0.1,
                description="Specialist for code generation, file modification, and math.",
            ),
        }

    def get_model(self, role: str) -> ModelConfig:
        """Get a model config by role name."""
        if role not in self.models:
            raise ValueError(f"Unknown model role: {role}. Available: {list(self.models.keys())}")
        return self.models[role]

    def validate(self) -> bool:
        """Validate that all required configuration is present."""
        errors = []
        if not self.groq_api_key:
            errors.append("GROQ_API_KEY is not set")
        if not self.openrouter_api_key:
            errors.append("OPENROUTER_API_KEY is not set")
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
        return True
