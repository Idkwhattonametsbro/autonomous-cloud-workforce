#!/usr/bin/env python3
"""
Autonomous Cloud Workforce — Command Center Dashboard
Full-featured server with: real-time agent monitoring, persistent memory,
analytics, multi-agent orchestration, auth, and PWA support.
"""

import json
import logging
import os
import random
import sys
import threading
import time
import hashlib
import uuid
from datetime import datetime, timezone
from collections import deque
from typing import Dict, Any, Optional, List
from functools import wraps

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, jsonify, request, session, redirect
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from src.config import AppConfig
from src.tools import create_default_registry
from src.agent import ReActAgent
from dashboard.memory import MemoryStore
from dashboard.analytics import AnalyticsStore
from dashboard.self_improve import SelfImprover, TaskPlanner
from src.intelligence import AdvancedIntelligence
from src.memory_advanced import AdvancedMemory
from src.infrastructure import (
    RateLimiter, CircuitBreaker, AuditLog, StateExporter,
    GracefulShutdown, ResourceMonitor, BatchProcessor, CostTracker
)

# ─── App Setup ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("dashboard")

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"),
            static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))

# Enable CORS for all routes
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

app.config["SECRET_KEY"] = os.getenv("DASHBOARD_SECRET", "dev-secret-change-me")

# Auth config
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")  # Empty = no auth

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Persistent stores
memory = MemoryStore()
analytics = AnalyticsStore()
improver = SelfImprover(memory)
planner = TaskPlanner()

# Advanced intelligence & infrastructure
advanced_intel = AdvancedIntelligence(memory)
advanced_memory = AdvancedMemory(memory)
rate_limiter = RateLimiter(memory)
circuit_breaker = CircuitBreaker(memory)
audit_log = AuditLog(memory)
state_exporter = StateExporter(memory, analytics)
graceful_shutdown = GracefulShutdown(state_exporter)
resource_monitor = ResourceMonitor()
batch_processor = BatchProcessor(memory)
cost_tracker = CostTracker(memory)

# ─── Multi-Agent State ──────────────────────────────────────

class AgentInstance:
    """Represents a single running agent."""
    def __init__(self, agent_id: str, goal: str):
        self.id = agent_id
        self.goal = goal
        self.status = "idle"
        self.iteration = 0
        self.max_iterations = 15
        self.start_time: Optional[float] = None
        self.tools_used: Dict[str, int] = {}
        self.events: deque = deque(maxlen=200)
        self.agent: Optional[ReActAgent] = None
        self.created_at = datetime.now(timezone.utc).isoformat()

class DashboardState:
    """Global dashboard state managing multiple agents."""
    def __init__(self):
        self.lock = threading.RLock()  # RLock = reentrant, prevents deadlock on nested acquire
        self.agents: Dict[str, AgentInstance] = {}
        self.primary_id: Optional[str] = None
        self.chat_history: List[Dict] = []
        self.total_runs = 0
        self.total_iterations = 0
        # Seed default memories
        memory.remember("agent_name", "Atlas-7", "identity")
        memory.remember("agent_version", "1.0.0", "identity")
        memory.remember("framework", "ReAct (Reasoning + Acting)", "identity")

state = DashboardState()


def get_or_create_primary() -> AgentInstance:
    """Get the primary agent instance, creating one if needed."""
    with state.lock:
        if not state.primary_id or state.primary_id not in state.agents:
            aid = str(uuid.uuid4())[:8]
            inst = AgentInstance(aid, "")
            state.agents[aid] = inst
            state.primary_id = aid
        return state.agents[state.primary_id]


def make_event_callback(agent_inst: AgentInstance):
    """Create an event callback scoped to a specific agent instance."""
    def callback(event_type: str, data: Dict[str, Any]):
        ts = datetime.now(timezone.utc).isoformat()
        payload = {"event_type": event_type, "timestamp": ts, "agent_id": agent_inst.id, "data": data}
        agent_inst.events.append(payload)

        with state.lock:
            if event_type == "agent_start":
                agent_inst.status = "running"
                agent_inst.goal = data.get("goal", "")
                agent_inst.start_time = time.time()
                agent_inst.iteration = 0
                agent_inst.tools_used = {}
            elif event_type == "iteration_start":
                agent_inst.status = "thinking"
                agent_inst.iteration = data.get("iteration", 0)
            elif event_type == "thinking":
                agent_inst.status = "thinking"
            elif event_type == "tool_executing":
                agent_inst.status = "executing"
                tool = data.get("tool_name", "unknown")
                agent_inst.tools_used[tool] = agent_inst.tools_used.get(tool, 0) + 1
            elif event_type == "tool_result":
                agent_inst.status = "thinking"
            elif event_type == "agent_complete":
                agent_inst.status = "idle"
                state.total_runs += 1
                state.total_iterations += agent_inst.iteration
            elif event_type == "report":
                agent_inst.status = "idle"
                # Record analytics
                analytics.record_run(
                    goal=agent_inst.goal,
                    status="completed" if data.get("completed") else "partial",
                    iterations=data.get("iterations", 0),
                    duration=data.get("elapsed_seconds", 0),
                    tools_used=agent_inst.tools_used,
                    agent_id=agent_inst.id,
                )
                # Self-improvement: analyze this run and evolve
                try:
                    analysis = improver.analyze_run(data, list(agent_inst.events))
                    socketio.emit("self_improvement", {
                        "analysis": analysis,
                        "performance": improver.get_performance_summary(),
                    })
                except Exception as e:
                    logger.warning(f"Self-improvement analysis failed: {e}")
            elif event_type == "iteration_error":
                agent_inst.status = "error"
            elif event_type == "connection_needed":
                # Relay to frontend — show connection request bubble
                socketio.emit("info_request", {
                    "task": agent_inst.goal,
                    "pattern": data.get("tool", ""),
                    "requests": data.get("required_fields", []),
                    "security_note": data.get("message", "Your data is stored locally and encrypted."),
                    "get_link": data.get("get_link", ""),
                    "display_name": data.get("display_name", ""),
                    "instructions": data.get("get_instructions", ""),
                })

        socketio.emit("agent_event", payload)
    return callback


def run_agent_thread(agent_inst: AgentInstance, goal: str, demo: bool = False):
    """Run an agent in a background thread."""
    try:
        cb = make_event_callback(agent_inst)
        if demo:
            _run_demo(agent_inst, goal, cb)
        else:
            os.environ.setdefault("GROQ_API_KEY", "demo-key")
            os.environ.setdefault("OPENROUTER_API_KEY", "demo-key")
            config = AppConfig()
            config.validate()
            tools = create_default_registry()
            agent = ReActAgent(config=config, tools=tools, event_callback=cb)
            agent_inst.agent = agent
            report = agent.run(goal=goal)
            cb("report", report)
    except Exception as e:
        logger.error(f"Agent {agent_inst.id} failed: {e}")
        with state.lock:
            agent_inst.status = "error"
        socketio.emit("agent_event", {
            "event_type": "error", "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_inst.id, "data": {"error": str(e)},
        })
    finally:
        agent_inst.agent = None
        with state.lock:
            if agent_inst.status != "error":
                agent_inst.status = "idle"


def _run_demo(agent_inst: AgentInstance, goal: str, cb):
    """Simulated demo run."""
    tools_pool = [
        ("scan_inbox", {"new_messages": random.randint(1,5)}),
        ("read_database", {"row_count": random.randint(3,20), "table": "clients"}),
        ("draft_reply", {"message_id": f"msg_{random.randint(1000,9999)}"}),
        ("update_crm", {"contact_id": f"crm_{random.randint(100,999)}"}),
        ("web_search", {"query": "market trends", "results_count": random.randint(5,50)}),
        ("log_task", {"task_name": "process_inquiry"}),
    ]
    thoughts = [
        "Analyzing the goal. I need to scan the inbox for pending client inquiries.",
        "Found messages. Let me read through them to understand each client's needs.",
        "This is a pricing inquiry. I'll draft a professional response with our rate card.",
        "Updating the CRM to log this interaction and mark the lead as engaged.",
        "Checking the database for existing client history to inform my strategy.",
        "Searching for latest market data to include relevant context.",
        "All inquiries processed. Logging completed tasks and finalizing.",
    ]

    cb("agent_start", {"goal": goal})
    time.sleep(0.5)
    max_iter = random.randint(5, 8)

    for i in range(1, max_iter + 1):
        cb("iteration_start", {"iteration": i, "max_iterations": max_iter})
        time.sleep(0.3)
        cb("thinking", {"phase": "think_and_decide"})
        time.sleep(0.5)
        thought = thoughts[min(i-1, len(thoughts)-1)]
        cb("model_response", {"content": thought, "has_tool_calls": True, "model_role": "task_manager", "confidence": round(random.uniform(0.85,0.99),2)})
        time.sleep(0.3)
        tn, td = tools_pool[i % len(tools_pool)]
        cb("tool_decision", {"tool_name": tn, "arguments": json.dumps(td), "reasoning": f"Selected {tn} for the next step."})
        time.sleep(0.2)
        cb("tool_executing", {"tool_name": tn, "arguments": td})
        time.sleep(random.uniform(0.2, 0.6))
        result = json.dumps({"status":"success", **td, "at": datetime.now(timezone.utc).isoformat()})
        cb("tool_result", {"tool_name": tn, "result": result, "elapsed_seconds": round(random.uniform(0.05,0.4),3)})
        time.sleep(0.2)
        cb("observation", {"num_tool_results":1, "conversation_length": i*3, "analysis": f"{tn} executed successfully."})
        time.sleep(0.3)

    cb("agent_complete", {"summary": f"Completed {max_iter} iterations. All tasks processed."})
    time.sleep(0.2)
    report = {"goal":goal, "iterations":max_iter, "elapsed_seconds":round(random.uniform(6,15),2), "completed":True, "summary":"All tasks completed.", "timestamp":datetime.now(timezone.utc).isoformat(), "conversation_turns":max_iter*3}
    cb("report", report)


# ─── Smart Chat ──────────────────────────────────────────────

def get_chat_response(message: str) -> str:
    msg = message.lower().strip()
    primary = get_or_create_primary()
    if any(w in msg for w in ["hi","hello","hey","sup"]):
        return random.choice([
            f"Hey there! I'm currently {primary.status}. What would you like me to work on?",
            "Hello! Ready to tackle some tasks. Just tell me what you need!",
        ])
    elif any(w in msg for w in ["status","what are you doing","what's up"]):
        extras = {"idle":"Waiting for my next task.","running":"Actively working on a goal.","thinking":"Mid-reasoning cycle.","executing":"Executing a tool right now."}
        return f"I'm currently **{primary.status}**. {extras.get(primary.status, 'Working through tasks.')}"
    elif any(w in msg for w in ["what can you do","capabilities","tools","help"]):
        return "My toolkit:\n- Scan Inbox — Check for messages\n- Draft Replies — Generate responses\n- Update CRM — Client records\n- Read Database — Query data\n- Web Search — Research\n- File Ops — Read/write files\n- Git — Commit and push"
    elif any(w in msg for w in ["memory","remember","recall"]):
        stats = memory.get_stats()
        return f"I have **{stats['total_memories']}** memories stored across {len(stats['categories'])} categories: {', '.join(stats['categories'].keys())}."
    elif any(w in msg for w in ["analytics","stats","performance","history"]):
        s = analytics.get_dashboard_stats()
        return f"**Analytics:**\n- {s['total_runs']} total runs\n- {s['success_rate']}% success rate\n- {s['avg_duration']}s avg duration\n- {s['runs_this_week']} runs this week"
    else:
        return random.choice([
            f"Noted: \"{message[:40]}\". I'll incorporate this into my reasoning.",
            f"Understood. Let me weave \"{message[:25]}\" into my analysis.",
            "Processing that now. This will influence my next decision cycle.",
            f"Got it. I'll factor \"{message[:25]}\" into my workflow priorities.",
        ])


# ─── Auth Middleware ──────────────────────────────────────────

def check_auth():
    if not DASHBOARD_PASSWORD:
        return True
    return session.get("authenticated", False)

@app.before_request
def auth_middleware():
    if not DASHBOARD_PASSWORD:
        return
    if request.path == "/login":
        return
    if request.path.startswith("/static"):
        return
    if not check_auth():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect("/login")


# ─── Routes ──────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if not DASHBOARD_PASSWORD:
        return redirect("/")
    if request.method == "POST":
        pw = request.form.get("password", "")
        if hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest():
            session["authenticated"] = True
            return redirect("/")
        return render_template("login.html", error="Invalid password")
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login" if DASHBOARD_PASSWORD else "/")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/sw.js")
def service_worker():
    resp = app.make_response(app.send_static_file("sw.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp

@app.route("/api/status")
def api_status():
    primary = get_or_create_primary()
    with state.lock:
        agents_info = {}
        for aid, inst in state.agents.items():
            agents_info[aid] = {
                "id": inst.id, "goal": inst.goal, "status": inst.status,
                "iteration": inst.iteration, "max_iterations": inst.max_iterations,
                "tools_used": inst.tools_used,
                "uptime": round(time.time() - inst.start_time, 1) if inst.start_time else 0,
            }
        return jsonify({
            "status": primary.status, "goal": primary.goal,
            "iteration": primary.iteration, "max_iterations": primary.max_iterations,
            "total_runs": state.total_runs, "total_iterations": state.total_iterations,
            "tools_used": primary.tools_used,
            "agents": agents_info,
            "primary_id": state.primary_id,
            "memory_stats": memory.get_stats(),
        })

@app.route("/api/events")
def api_events():
    primary = get_or_create_primary()
    return jsonify(list(primary.events))

@app.route("/api/events/<agent_id>")
def api_agent_events(agent_id):
    with state.lock:
        inst = state.agents.get(agent_id)
    if not inst:
        return jsonify([])
    return jsonify(list(inst.events))

@app.route("/api/tools")
def api_tools():
    registry = create_default_registry()
    return jsonify([{"name": n, **(registry.get_tool_info(n) or {})} for n in registry.list_tools()])

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json() or {}
    goal = data.get("goal", "Check for new client inquiries and draft responses.")
    demo = data.get("demo", False)
    agent_id = data.get("agent_id")

    with state.lock:
        if agent_id and agent_id in state.agents:
            inst = state.agents[agent_id]
            if inst.status in ("running", "thinking", "executing"):
                return jsonify({"error": "Agent already running"}), 409
        else:
            inst = get_or_create_primary()
            if inst.status in ("running", "thinking", "executing"):
                return jsonify({"error": "Agent already running"}), 409

    has_keys = all(os.getenv(k, "demo-key") not in ("demo-key", "") for k in ["GROQ_API_KEY", "OPENROUTER_API_KEY"])
    thread = threading.Thread(target=run_agent_thread, args=(inst, goal, demo or not has_keys), daemon=True)
    thread.start()
    return jsonify({"status": "started", "goal": goal, "agent_id": inst.id})

@app.route("/api/agents", methods=["GET", "POST"])
def api_agents():
    """List or spawn agent instances."""
    if request.method == "POST":
        data = request.get_json() or {}
        goal = data.get("goal", "Autonomous task processing")
        aid = str(uuid.uuid4())[:8]
        inst = AgentInstance(aid, goal)
        with state.lock:
            state.agents[aid] = inst
        return jsonify({"agent_id": aid, "status": "created"})
    with state.lock:
        return jsonify([{
            "id": a.id, "goal": a.goal, "status": a.status,
            "iteration": a.iteration, "created_at": a.created_at,
        } for a in state.agents.values()])

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json() or {}
    msg = data.get("message", "")
    if not msg:
        return jsonify({"error": "Message required"}), 400

    state.chat_history.append({"role": "user", "content": msg, "timestamp": datetime.now(timezone.utc).isoformat()})
    memory.log_interaction("user", msg)
    resp = get_chat_response(msg)
    state.chat_history.append({"role": "assistant", "content": resp, "timestamp": datetime.now(timezone.utc).isoformat()})
    memory.log_interaction("assistant", resp)
    return jsonify({"response": resp})

@app.route("/api/chat/history")
def api_chat_history():
    # Combine in-memory + persisted
    persisted = memory.get_recent_interactions(30)
    return jsonify(state.chat_history[-30:] if state.chat_history else persisted)

@app.route("/api/memory", methods=["GET", "POST", "DELETE"])
def api_memory():
    if request.method == "POST":
        data = request.get_json() or {}
        memory.remember(data.get("key",""), data.get("value",""), data.get("category","general"))
        return jsonify({"status": "saved"})
    elif request.method == "DELETE":
        data = request.get_json() or {}
        memory.forget(data.get("key",""), data.get("category","general"))
        return jsonify({"status": "deleted"})
    cat = request.args.get("category", "")
    if cat:
        return jsonify(memory.recall_category(cat))
    return jsonify(memory.get_stats())

@app.route("/api/analytics")
def api_analytics():
    return jsonify(analytics.get_dashboard_stats())

@app.route("/api/analytics/runs")
def api_analytics_runs():
    return jsonify(analytics.get_recent_runs())

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json() or {}
        with state.lock:
            if "max_iterations" in data:
                for inst in state.agents.values():
                    inst.max_iterations = int(data["max_iterations"])
        return jsonify({"status": "updated"})
    primary = get_or_create_primary()
    return jsonify({"max_iterations": primary.max_iterations, "agents_count": len(state.agents)})


@app.route("/api/task/plan", methods=["POST"])
def api_task_plan():
    """Analyze a task request and determine if info is needed."""
    data = request.get_json() or {}
    task = data.get("task", "")
    if not task:
        return jsonify({"error": "Task description required"}), 400

    result = planner.analyze_task(task)

    # If ready to execute, also return evolution stage
    if result["status"] == "ready":
        result["evolution"] = improver.get_performance_summary()

    return jsonify(result)


@app.route("/api/task/execute", methods=["POST"])
def api_task_execute():
    """Execute a task with provided credentials/info."""
    data = request.get_json() or {}
    task = data.get("task", "")
    credentials = data.get("credentials", {})

    if not task:
        return jsonify({"error": "Task description required"}), 400

    # Store provided credentials securely in memory
    for key, value in credentials.items():
        if value:
            memory.remember(key, value, "user_credentials", source="user_input", confidence=1.0)

    # Now plan again — should be ready this time
    result = planner.analyze_task(task)

    if result["status"] == "ready":
        # Launch the agent with this goal
        inst = get_or_create_primary()
        with state.lock:
            if inst.status in ("running", "thinking", "executing"):
                return jsonify({"error": "Agent already running"}), 409

        has_keys = all(os.getenv(k, "demo-key") not in ("demo-key", "") for k in ["GROQ_API_KEY", "OPENROUTER_API_KEY"])
        thread = threading.Thread(target=run_agent_thread, args=(inst, task, not has_keys), daemon=True)
        thread.start()
        return jsonify({"status": "started", "goal": task, "agent_id": inst.id})
    else:
        return jsonify({"status": "still_needs_info", "requests": result.get("requests", [])})


@app.route("/api/self-improve/status")
def api_self_improve_status():
    """Get the agent's current self-improvement status."""
    perf = improver.get_performance_summary()
    strategy = improver.get_current_strategy()
    return jsonify({
        "performance": perf,
        "strategy": strategy,
        "memory_stats": memory.get_stats(),
    })


@app.route("/api/self-improve/analyze", methods=["POST"])
def api_self_improve_analyze():
    """Manually trigger self-improvement analysis on the last run."""
    primary = get_or_create_primary()
    events = list(primary.events)
    last_report = None
    for evt in reversed(events):
        if evt.get("event_type") == "report":
            last_report = evt.get("data", {})
            break
    if not last_report:
        return jsonify({"message": "No completed runs to analyze yet."})
    analysis = improver.analyze_run(last_report, events)
    return jsonify({"analysis": analysis, "performance": improver.get_performance_summary()})



# ─── Infrastructure Endpoints ────────────────────────────────

@app.route("/api/state/export")
def api_state_export():
    """Export the agent's full state."""
    audit_log.log("state_export", {"action": "export"})
    return jsonify(state_exporter.export_state())

@app.route("/api/state/import", methods=["POST"])
def api_state_import():
    """Import agent state from JSON."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    result = state_exporter.import_state(data)
    audit_log.log("state_import", {"memories_imported": result.get("memories_count", 0)})
    return jsonify(result)

@app.route("/api/audit-log")
def api_audit_log():
    """Get recent audit log entries."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify(audit_log.get_recent(limit))

@app.route("/api/costs")
def api_costs():
    """Get cost tracking report."""
    return jsonify(cost_tracker.get_report())

@app.route("/api/resources")
def api_resources():
    """Get resource usage report."""
    resource_monitor.take_sample("dashboard")
    return jsonify(resource_monitor.get_report())

@app.route("/api/queue", methods=["GET", "POST"])
def api_queue():
    """Manage processing queues."""
    queue_name = request.args.get("name", "default")
    if request.method == "POST":
        data = request.get_json() or {}
        batch_processor.queue_item(data, queue_name)
        return jsonify({"status": "queued", "queue_size": batch_processor.queue_size(queue_name)})
    batch_size = request.args.get("batch", 5, type=int)
    items = batch_processor.get_batch(queue_name, batch_size)
    return jsonify({"items": items, "remaining": batch_processor.queue_size(queue_name)})

@app.route("/api/circuit-breaker/<service>", methods=["GET", "POST", "DELETE"])
def api_circuit_breaker(service):
    """Manage circuit breakers."""
    if request.method == "GET":
        return jsonify({"open": circuit_breaker.is_open(service)})
    elif request.method == "POST":
        circuit_breaker.record_failure(service)
        return jsonify({"status": "failure_recorded", "open": circuit_breaker.is_open(service)})
    elif request.method == "DELETE":
        circuit_breaker.reset(service)
        return jsonify({"status": "reset"})

@app.route("/api/memories/consolidate", methods=["POST"])
def api_consolidate():
    """Trigger memory consolidation."""
    advanced_memory.consolidate_memories()
    advanced_memory.apply_forgetting_curve()
    return jsonify({"status": "consolidated"})

@app.route("/api/memories/episodes", methods=["GET", "POST"])
def api_episodes():
    """Manage episodic memories."""
    if request.method == "POST":
        data = request.get_json() or {}
        advanced_memory.store_episode(data)
        return jsonify({"status": "stored"})
    goal = request.args.get("goal", "")
    if goal:
        return jsonify(advanced_memory.recall_similar_episodes(goal))
    return jsonify(advanced_memory._get_episodes())

@app.route("/api/knowledge-graph")
def api_knowledge_graph():
    """Get or build the knowledge graph."""
    advanced_memory.build_knowledge_graph()
    graph_str = memory.recall("knowledge_graph", "graph")
    return jsonify(json.loads(graph_str) if graph_str else {"nodes": [], "edges": []})

@app.route("/api/performance")
def api_performance():
    """Get comprehensive performance report."""
    return jsonify({
        "self_improvement": improver.get_performance_summary(),
        "costs": cost_tracker.get_report(),
        "resources": resource_monitor.get_report(),
        "analytics": analytics.get_dashboard_stats(),
        "memory": memory.get_stats(),
    })


# ─── SocketIO ────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    primary = get_or_create_primary()
    with state.lock:
        emit("state_update", {
            "status": primary.status, "goal": primary.goal,
            "iteration": primary.iteration, "max_iterations": primary.max_iterations,
            "total_runs": state.total_runs, "total_iterations": state.total_iterations,
            "tools_used": primary.tools_used,
        })
    for evt in list(primary.events)[-50:]:
        emit("agent_event", evt)

@socketio.on("send_chat")
def handle_chat(data):
    msg = data.get("message", "")
    if not msg: return
    state.chat_history.append({"role":"user","content":msg,"timestamp":datetime.now(timezone.utc).isoformat()})
    memory.log_interaction("user", msg)

    # Check if this is a task that needs info gathering
    plan_result = planner.analyze_task(msg)

    if plan_result.get("status") == "needs_info":
        # Ask the frontend to show the info-gathering modal
        resp = "I can do that. I need a few details from you first — I'll show you a secure form."
        state.chat_history.append({"role":"assistant","content":resp,"timestamp":datetime.now(timezone.utc).isoformat()})
        memory.log_interaction("assistant", resp)
        emit("chat_response", {"content": resp, "timestamp": datetime.now(timezone.utc).isoformat()})
        # Emit the info request for the modal
        emit("info_request", {
            "task": msg,
            "pattern": plan_result.get("pattern", ""),
            "requests": plan_result.get("requests", []),
            "security_note": plan_result.get("security_note", "Your data is stored locally and encrypted."),
        })
    elif plan_result.get("status") == "ready" and any(kw in msg.lower() for kw in ["send", "create", "write", "update", "find", "search", "generate", "build"]):
        # It's an actionable task with all info available — execute directly
        resp = "On it. I have everything I need. Launching now..."
        state.chat_history.append({"role":"assistant","content":resp,"timestamp":datetime.now(timezone.utc).isoformat()})
        memory.log_interaction("assistant", resp)
        emit("chat_response", {"content": resp, "timestamp": datetime.now(timezone.utc).isoformat()})
        # Auto-launch
        has_keys = all(os.getenv(k, "demo-key") not in ("demo-key", "") for k in ["GROQ_API_KEY", "OPENROUTER_API_KEY"])
        inst = get_or_create_primary()
        thread = threading.Thread(target=run_agent_thread, args=(inst, msg, not has_keys), daemon=True)
        thread.start()
        emit("agent_event", {"event_type": "agent_start", "timestamp": datetime.now(timezone.utc).isoformat(), "data": {"goal": msg}})
    else:
        # Normal chat
        resp = get_chat_response(msg)
        state.chat_history.append({"role":"assistant","content":resp,"timestamp":datetime.now(timezone.utc).isoformat()})
        memory.log_interaction("assistant", resp)
        emit("chat_response", {"content": resp, "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/api/connections")
def api_connections():
    """Get list of connected tools/services."""
    connected = []
    
    # Check each integration
    if memory.recall("gmail_address", "user_credentials"):
        connected.append("gmail")
    if memory.recall("github_token", "user_credentials"):
        connected.append("github")
    if memory.recall("groq_api_key", "user_credentials") or os.getenv("GROQ_API_KEY"):
        connected.append("groq")
    if memory.recall("openrouter_api_key", "user_credentials") or os.getenv("OPENROUTER_API_KEY"):
        connected.append("openrouter")
    if memory.recall("paypal_email", "user_credentials"):
        connected.append("paypal")
    if memory.recall("slack_webhook", "user_credentials"):
        connected.append("slack")
    if memory.recall("notion_token", "user_credentials"):
        connected.append("notion")
    if memory.recall("db_url", "user_credentials"):
        connected.append("database")
    
    return jsonify({"connected": connected})


# ─── Start ───────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5000"))
    logger.info(f"🚀 Command Center on port {port} | Auth: {'ON' if DASHBOARD_PASSWORD else 'OFF'} | Memory: {memory.get_stats()}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
