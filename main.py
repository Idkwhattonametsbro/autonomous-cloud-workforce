#!/usr/bin/env python3
"""
Entry point for the Autonomous Cloud Workforce Agent.
This is what GitHub Actions will execute on each wake-up cycle.
"""

import logging
import sys
import os
import json
from datetime import datetime, timezone

# FIX: Use abspath to avoid empty string when run from same directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.config import AppConfig
from src.tools import create_default_registry
from src.agent import ReActAgent


def setup_logging():
    """Configure logging for both local and GitHub Actions environments."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_level = logging.DEBUG if os.getenv("VERBOSE", "true").lower() == "true" else logging.INFO

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Reduce noise from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    """Main execution flow."""
    setup_logging()
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info("🌅 AUTONOMOUS CLOUD WORKFORCE — AGENT WAKING UP")
    logger.info(f"   Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"   Environment: {'GitHub Actions' if os.getenv('GITHUB_ACTIONS') else 'Local'}")
    logger.info("=" * 60)

    # Step 1: Load and validate configuration
    logger.info("📋 Loading configuration...")
    config = AppConfig()
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"❌ Configuration validation failed:\n{e}")
        logger.info("💡 Set your API keys as environment variables or GitHub Secrets.")
        logger.info("   Required: GROQ_API_KEY, OPENROUTER_API_KEY")
        sys.exit(1)

    # Step 2: Initialize the tool registry
    logger.info("🔧 Initializing tools...")
    tools = create_default_registry()
    logger.info(f"   Available tools: {', '.join(tools.list_tools())}")

    # Step 3: Get the agent's goal
    goal = os.getenv("AGENT_GOAL", config.agent_goal)
    logger.info(f"🎯 Agent goal: {goal}")

    # Step 4: Run the ReAct loop
    logger.info("🔄 Starting ReAct loop...")
    agent = ReActAgent(config=config, tools=tools)

    try:
        report = agent.run(goal=goal)
    except Exception as e:
        logger.error(f"❌ Agent execution failed catastrophically: {e}")
        tools.execute("log_task", {
            "task_name": "agent_execution",
            "status": "failed",
            "details": str(e),
        })
        sys.exit(1)

    # Step 5: Output final report
    logger.info("\n" + "=" * 60)
    logger.info("📊 FINAL EXECUTION REPORT")
    logger.info("=" * 60)
    logger.info(json.dumps(report, indent=2, default=str))
    logger.info("=" * 60)

    # Step 6: Save report (FIX: use PROJECT_ROOT for reliable path)
    report_dir = os.path.join(PROJECT_ROOT, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(
        report_dir,
        f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"📄 Report saved to: {report_file}")

    # Step 7: Commit if in GitHub Actions
    if os.getenv("GITHUB_ACTIONS"):
        logger.info("📦 Committing reports to repository...")
        tools.execute("git_commit_and_push", {
            "message": f"🤖 Agent run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        })

    logger.info("💤 Agent entering deep sleep. Runner will shut down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
