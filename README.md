# 🤖 Autonomous Cloud Workforce

## A Self-Sustaining, Zero-Code AI Agent That Runs Forever in the Cloud

Your autonomous workforce agent — powered by free LLM APIs, running on GitHub Actions, and requiring **zero ongoing intervention**.

---

## 🧠 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     THE TRIGGER LAYER                            │
│                                                                  │
│   ⏰ Cron Schedule        🌐 Webhook          🖱️ Manual          │
│   (every 30 min)         (form submit)      (Actions tab)        │
└─────────────┬──────────────────┬──────────────────┬──────────────┘
              │                  │                  │
              ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│               GITHUB ACTIONS RUNNER (Free)                       │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              🔄 THE REACT LOOP                            │  │
│   │                                                           │  │
│   │   1. 🧠 THOUGHT — Analyze situation & identify next step  │  │
│   │   2. 🎯 DECISION — Choose the best tool for the job       │  │
│   │   3. ⚡ ACTION  — Execute the tool                        │  │
│   │   4. 👁️ OBSERVE — Read result, self-correct if needed     │  │
│   │                                                           │  │
│   │   ──→ Loops until goal is accomplished ──→                │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌────────────────────┐  ┌──────────────────────────────────┐  │
│   │  MODEL STRATEGY    │  │         TOOL SYSTEM              │  │
│   │                    │  │                                   │  │
│   │  Groq:             │  │  📧 Scan Inbox                    │  │
│   │  ├ Llama 3.3 70B  │  │  ✍️  Draft Reply                  │  │
│   │  │ (Task Manager)  │  │  📊 Update CRM                    │  │
│   │  │                 │  │  🗄️  Read Database                │  │
│   │  OpenRouter:       │  │  🔍 Web Search                    │  │
│   │  ├ Gemini 2.5 Flash│  │  📁 File Read/Write               │  │
│   │  │ (Data Reader)   │  │  📦 Git Commit/Push               │  │
│   │  ├ Qwen 2.5 Coder  │  │  📋 Log Task                     │  │
│   │  │ (Code Specialist)│  │                                   │  │
│   └────────────────────┘  └──────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DEEP SLEEP                                   │
│                                                                  │
│   Runner shuts down. Logs & reports committed to repo.           │
│   No cost incurred while sleeping. Wakes on next trigger.        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (5 Minutes)

### 1. Fork This Repository

Click the **Fork** button at the top of this page.

### 2. Add Your Free API Keys

Go to your fork → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these two secrets:

| Secret Name | Where to Get It | Cost |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Free |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | Free |

### 3. Enable the Workflow

Go to the **Actions** tab → Click **"I understand my workflows, go ahead and enable them"**

### 4. Wake It Up Manually (Optional)

Click the **🤖 Autonomous Agent** workflow → **Run workflow** → **Run workflow**

Your agent will wake up, execute its ReAct loop, and go back to sleep — all in ~30 seconds.

### 5. It Runs Forever

The cron schedule is set to `*/30 * * * *` (every 30 minutes). Your agent will autonomously wake up, work, and sleep 24/7 without any intervention.

---

## 📁 Project Structure

```
autonomous-cloud-workforce/
├── .github/
│   └── workflows/
│       └── agent.yml              # GitHub Actions workflow (cron + manual + webhook)
├── src/
│   ├── __init__.py
│   ├── agent.py                   # Core ReAct loop engine
│   ├── config.py                  # Configuration & model registry
│   ├── models.py                  # Groq + OpenRouter API routing
│   └── tools.py                   # Tool definitions & registry
├── main.py                        # Entry point (what GitHub Actions executes)
├── requirements.txt               # Python dependencies
├── .env.example                   # Template for local development
├── .gitignore
└── README.md                      # This file
```

---

## 🔄 How the ReAct Loop Works

Unlike a rigid script with hardcoded steps, your agent **thinks dynamically**:

```
┌─────────────────────────────────────────────────────┐
│                  ITERATION 1                         │
│                                                      │
│  THOUGHT: "I need to check if there are new emails"  │
│  DECISION: "I'll use the scan_inbox tool"            │
│  ACTION:  scan_inbox()                               │
│  OBSERVATION: "Found 2 new messages"                 │
└────────────────────────┬────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│                  ITERATION 2                         │
│                                                      │
│  THOUGHT: "I have 2 new messages, let me read them"  │
│  DECISION: "I'll read the first message"             │
│  ACTION:  read_database(message_1)                   │
│  OBSERVATION: "It's a pricing inquiry from Acme"     │
└────────────────────────┬────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│                  ITERATION 3                         │
│                                                      │
│  THOUGHT: "I need to draft a reply about pricing"    │
│  DECISION: "Use draft_reply with professional tone"  │
│  ACTION:  draft_reply(msg_id, context, tone)         │
│  OBSERVATION: "Draft created successfully"           │
└────────────────────────┬────────────────────────────┘
                         ▼
                    ... continues ...
                         ▼
┌─────────────────────────────────────────────────────┐
│                  FINAL ITERATION                     │
│                                                      │
│  THOUGHT: "All tasks are complete"                   │
│  DECISION: "Log completion and finish"               │
│  ACTION:  log_task("all_done", "completed")          │
│  OBSERVATION: "TASK_COMPLETE"                        │
└─────────────────────────────────────────────────────┘
```

### Self-Correction in Action

If a tool fails, the agent doesn't crash — it **adapts**:

```
  OBSERVATION: "scan_inbox() failed: Authentication error"
  THOUGHT: "The inbox tool failed. Let me try reading the database 
            directly for pending messages instead."
  DECISION: "Use read_database as a fallback"
  ACTION:  read_database("pending", "messages")
  OBSERVATION: "Success! Found 3 pending messages in database"
```

---

## 🧠 The Model Strategy

Your agent intelligently routes tasks to the best free model:

| Role | Model | Provider | Best For |
|---|---|---|---|
| **Task Manager** | Llama 3.3 70B | Groq | Planning, decision-making, function calling |
| **Data Reader** | Gemini 2.5 Flash | OpenRouter | Large documents, massive context processing |
| **Code Specialist** | Qwen 2.5 Coder 32B | OpenRouter | Code generation, file modification, math |

The task manager (Llama 3.3 70B on Groq) serves as the executive brain because:
- **Free** on Groq's platform
- **Elite logic** capabilities for structured reasoning
- **Blazing fast** — Groq runs on custom LPU hardware (~500 tokens/sec)
- **Native function calling** — designed for tool use

When a sub-task requires reading massive data (like a 200-page document), the agent dynamically routes it to Gemini 2.5 Flash. When code needs to be written or modified, it falls to Qwen 2.5 Coder.

---

## 🔧 Customizing Tools

### Adding a New Tool

Open `src/tools.py` and add your tool:

```python
def _my_new_tool(param1: str, param2: int = 10) -> Dict[str, Any]:
    """Your tool's logic here."""
    # Connect to any API, database, or service
    return {"result": "success", "data": ...}

# Register it in create_default_registry():
registry.register(
    name="my_new_tool",
    description="What this tool does (the LLM reads this!)",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer", "description": "..."},
        },
        "required": ["param1"],
    },
    handler=_my_new_tool,
    category="my_category",
)
```

That's it! The agent automatically discovers the new tool and can use it in its ReAct loop.

### Integration Points

The built-in tools have clearly marked `# --- INTEGRATION POINT ---` comments where you connect real services:

| Tool | Integration |
|---|---|
| `scan_inbox` | Gmail API, Outlook, or any email provider |
| `update_crm` | HubSpot, Salesforce, Pipedrive |
| `read_database` | PostgreSQL, MySQL, SQLite |
| `web_search` | Tavily, SerpAPI, Brave Search |

---

## ⚡ Trigger Options

### Cron Schedule (Automatic)
Edit `.github/workflows/agent.yml` to change the schedule:
```yaml
schedule:
  - cron: '*/30 * * * *'   # Every 30 minutes (default)
  # - cron: '*/15 * * * *'  # Every 15 minutes
  # - cron: '0 * * * *'     # Every hour
  # - cron: '0 */6 * * *'   # Every 6 hours
```

### Manual Trigger
Go to **Actions** → **🤖 Autonomous Agent** → **Run workflow**

You can also override the agent's goal for a single run.

### Webhook Trigger
External services can trigger the agent via GitHub's `repository_dispatch` API:

```bash
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOU/autonomous-cloud-workforce/dispatches \
  -d '{"event_type": "agent_trigger", "client_payload": {"goal": "Process refund for customer #1234"}}'
```

---

## 💰 Cost Breakdown

| Component | Cost |
|---|---|
| Groq API (Llama 3.3 70B) | **Free** |
| OpenRouter (Gemini 2.5 Flash) | **Free** |
| OpenRouter (Qwen 2.5 Coder) | **Free** |
| GitHub Actions (2,000 min/month) | **Free** |
| **Total** | **$0/month** |

### Why It Stays Free

- Each agent run takes ~30-45 seconds
- At every 30 minutes: ~48 runs/day × 0.75 min = **36 minutes/day**
- Monthly: ~1,080 minutes — well within GitHub's 2,000 free minutes
- All three LLM providers offer free tiers with generous limits

---

## 📊 Monitoring

The agent self-logs everything:

- **`logs/task_history.jsonl`** — Every action the agent took, line by line
- **`reports/run_YYYYMMDD_HHMMSS.json`** — Full execution report per run
- **GitHub Actions tab** — Live logs for each run

Check the Actions tab anytime to see exactly what the agent did during each cycle.

---

## 🔐 Security

- API keys are stored as **GitHub Secrets** — never in code
- Each run executes in an **isolated runner** that's destroyed after completion
- No persistent server or open port to attack
- The agent's file writes are tracked in git history for full auditability

---

## 🛠️ Local Development

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/autonomous-cloud-workforce.git
cd autonomous-cloud-workforce

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

---

## 🎯 Example Use Cases

| Use Case | Goal Setting |
|---|---|
| **Customer Support** | "Scan inbox for new inquiries, draft professional replies, and update CRM" |
| **Lead Qualification** | "Check form submissions, qualify leads, update pipeline, flag hot leads" |
| **Data Entry** | "Read incoming documents, extract key data, update database records" |
| **Social Media** | "Check mentions, draft engagement responses, schedule posts" |
| **DevOps** | "Check deployment logs, identify errors, create GitHub issues" |
| **Research** | "Monitor industry news, summarize findings, update knowledge base" |

Change the goal by editing the `AGENT_GOAL` secret in your repository settings.

---

## 📝 License

MIT — Use freely, modify as you wish, build your autonomous empire.
