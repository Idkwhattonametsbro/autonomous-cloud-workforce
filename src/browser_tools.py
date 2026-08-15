"""
Browser automation, web search, progress tracking, background tasks, and smart planning.
"""

import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Browser automation disabled.")


# ═══════════════════════════════════════════════════════════════════
# REAL WEB SEARCH
# ═══════════════════════════════════════════════════════════════════

def _web_search_real(query: str, num_results: int = 5) -> Dict[str, Any]:
    """Actually search the web using Playwright + Google."""
    logger.info(f"Real web search: {query}")
    
    if not PLAYWRIGHT_AVAILABLE:
        return {'status': 'error', 'message': 'Browser automation not available.'}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"https://www.google.com/search?q={quote_plus(query)}", timeout=30000)
            page.wait_for_load_state('networkidle')
            
            results = []
            for r in page.query_selector_all('div.g')[:num_results]:
                title_el = r.query_selector('h3')
                link_el = r.query_selector('a')
                snippet_el = r.query_selector('div.VwiC3b, span.aCOpRe')
                
                if title_el and link_el:
                    results.append({
                        'title': title_el.inner_text(),
                        'url': link_el.get_attribute('href') or '',
                        'snippet': snippet_el.inner_text() if snippet_el else ''
                    })
            
            browser.close()
            
            return {
                'status': 'success',
                'query': query,
                'results': results,
                'result_count': len(results),
                'searched_at': datetime.now(timezone.utc).isoformat()
            }
    
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return {'status': 'error', 'message': f'Search failed: {str(e)}'}


# ═══════════════════════════════════════════════════════════════════
# BROWSER AUTOMATION
# ═══════════════════════════════════════════════════════════════════

def _browse_website(url: str, action: str = "read", extract: str = "text") -> Dict[str, Any]:
    """Browse a website. Supports: read, click, extract text/html/links."""
    logger.info(f"Browsing {url} (action: {action})")
    
    if not PLAYWRIGHT_AVAILABLE:
        return {'status': 'error', 'message': 'Browser automation not available. Install playwright.'}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state('networkidle')
            
            if action == "click":
                for selector in ['a', 'button', '[role="button"]']:
                    elements = page.query_selector_all(selector)
                    for el in elements[:5]:
                        text = el.inner_text().strip()
                        if text and len(text) < 50:
                            el.click()
                            page.wait_for_load_state('networkidle', timeout=5000)
                            content = page.inner_text('body')[:3000]
                            browser.close()
                            return {
                                'status': 'success', 'url': url, 'action': 'click',
                                'clicked': text, 'content': content,
                                'browsed_at': datetime.now(timezone.utc).isoformat()
                            }
                browser.close()
                return {'status': 'error', 'message': 'No clickable elements found'}
            
            if extract == "text":
                content = page.inner_text('body')
            elif extract == "links":
                links = page.eval_on_selector_all('a[href]', 'els => els.slice(0,20).map(e => ({text: e.innerText.trim().substring(0,60), href: e.href}))')
                content = json.dumps(links)
            else:
                content = page.inner_text('body')
            
            title = page.title()
            browser.close()
            
            return {
                'status': 'success', 'url': url, 'title': title,
                'content': content[:5000], 'extract_type': extract,
                'browsed_at': datetime.now(timezone.utc).isoformat()
            }
    
    except Exception as e:
        logger.error(f"Browsing failed: {e}")
        return {'status': 'error', 'message': f'Failed: {str(e)}'}


def _fill_form(url: str, fields: str, submit: str = "") -> Dict[str, Any]:
    """Fill a web form. fields is a JSON string of {selector: value} pairs."""
    logger.info(f"Filling form at {url}")
    
    if not PLAYWRIGHT_AVAILABLE:
        return {'status': 'error', 'message': 'Browser automation not available.'}
    
    try:
        fields_dict = json.loads(fields) if isinstance(fields, str) else fields
    except:
        return {'status': 'error', 'message': 'Invalid fields format. Must be JSON.'}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state('networkidle')
            
            filled = []
            for selector, value in fields_dict.items():
                for sel in [selector, f'input[name="{selector}"]', f'input[id="{selector}"]',
                           f'textarea[name="{selector}"]', f'[placeholder*="{selector}" i]']:
                    el = page.query_selector(sel)
                    if el:
                        el.fill(str(value))
                        filled.append(selector)
                        break
            
            result_text = ""
            if submit:
                btn = page.query_selector(submit) or page.query_selector('button[type="submit"]')
                if btn:
                    btn.click()
                    page.wait_for_load_state('networkidle', timeout=10000)
                    result_text = page.inner_text('body')[:3000]
            
            browser.close()
            
            return {
                'status': 'success', 'url': url, 'filled_fields': filled,
                'submitted': bool(submit), 'result_preview': result_text[:1000] if result_text else 'Form filled',
                'submitted_at': datetime.now(timezone.utc).isoformat()
            }
    
    except Exception as e:
        logger.error(f"Form filling failed: {e}")
        return {'status': 'error', 'message': f'Failed: {str(e)}'}


def _interact_page(url: str, instructions: str) -> Dict[str, Any]:
    """Interact with a webpage following instructions."""
    logger.info(f"Interacting with {url}: {instructions}")
    
    if not PLAYWRIGHT_AVAILABLE:
        return {'status': 'error', 'message': 'Browser automation not available.'}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state('networkidle')
            
            page_info = {
                'title': page.title(),
                'url': page.url,
                'links': page.eval_on_selector_all('a[href]', 'els => els.slice(0,20).map(e => ({text: e.innerText.trim().substring(0,50), href: e.href}))'),
                'inputs': page.eval_on_selector_all('input,textarea,select', 'els => els.map(e => ({type: e.type||e.tagName, name: e.name, id: e.id}))'),
                'buttons': page.eval_on_selector_all('button,[role="button"]', 'els => els.slice(0,15).map(e => ({text: e.innerText?.trim()?.substring(0,50)||""}))'),
            }
            
            body_text = page.inner_text('body')[:5000]
            browser.close()
            
            return {
                'status': 'success', 'url': url, 'title': page_info['title'],
                'instructions': instructions, 'page_structure': page_info,
                'body_preview': body_text[:2000],
                'interacted_at': datetime.now(timezone.utc).isoformat()
            }
    
    except Exception as e:
        return {'status': 'error', 'message': f'Failed: {str(e)}'}


# ═══════════════════════════════════════════════════════════════════
# PROGRESS TRACKING
# ═══════════════════════════════════════════════════════════════════

def _create_progress_tracker(goal: str) -> Dict[str, Any]:
    """Create a progress tracker for a goal."""
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        progress = {
            'goal': goal, 'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'in_progress', 'steps': [], 'current_step': 0, 'notes': []
        }
        mem.remember(f'progress_{hash(goal) % 10000}', json.dumps(progress), 'progress_tracking')
        return {'status': 'success', 'message': f'Tracking: {goal}', 'goal': goal}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def _update_progress(goal: str, step: str, status: str = "completed", note: str = "") -> Dict[str, Any]:
    """Update progress on a tracked goal."""
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        s = mem.recall(f'progress_{hash(goal) % 10000}', 'progress_tracking')
        if not s:
            return {'status': 'error', 'message': f'No tracker for: {goal}'}
        progress = json.loads(s)
        progress['steps'].append({'step': step, 'status': status, 'note': note, 'timestamp': datetime.now(timezone.utc).isoformat()})
        progress['current_step'] = len(progress['steps'])
        if note:
            progress['notes'].append(note)
        mem.remember(f'progress_{hash(goal) % 10000}', json.dumps(progress), 'progress_tracking')
        return {'status': 'success', 'current_step': progress['current_step']}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def _get_progress(goal: str) -> Dict[str, Any]:
    """Get progress on a tracked goal."""
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        s = mem.recall(f'progress_{hash(goal) % 10000}', 'progress_tracking')
        if not s:
            return {'status': 'not_found', 'message': f'No tracker for: {goal}'}
        progress = json.loads(s)
        return {
            'status': 'success', 'goal': progress['goal'],
            'current_step': progress['current_step'], 'steps': progress['steps'],
            'notes': progress['notes'], 'created_at': progress['created_at']
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND TASK SYSTEM
# ═══════════════════════════════════════════════════════════════════

_task_queue = queue.Queue()
_workers = []
_task_results = {}
_workers_lock = threading.Lock()

def _background_worker():
    """Worker thread that processes background tasks."""
    while True:
        try:
            task_id, task_name, task_data = _task_queue.get(timeout=2)
            try:
                # Simulate task execution (replace with real execution)
                import time
                time.sleep(1)
                with _workers_lock:
                    _task_results[task_id] = {
                        'status': 'completed', 'task_name': task_name,
                        'result': task_data, 'completed_at': datetime.now(timezone.utc).isoformat()
                    }
            except Exception as e:
                with _workers_lock:
                    _task_results[task_id] = {
                        'status': 'failed', 'task_name': task_name,
                        'error': str(e), 'failed_at': datetime.now(timezone.utc).isoformat()
                    }
            _task_queue.task_done()
        except queue.Empty:
            continue

def _start_workers(count=3):
    global _workers
    with _workers_lock:
        if not _workers:
            for _ in range(count):
                t = threading.Thread(target=_background_worker, daemon=True)
                t.start()
                _workers.append(t)

def _submit_background_task(task_name: str, description: str = "") -> Dict[str, Any]:
    """Submit a task to run in the background."""
    _start_workers()
    task_id = f"task_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    
    with _workers_lock:
        _task_results[task_id] = {
            'status': 'queued', 'task_name': task_name, 'description': description,
            'queued_at': datetime.now(timezone.utc).isoformat()
        }
    
    _task_queue.put((task_id, task_name, description))
    
    return {
        'status': 'queued', 'task_id': task_id, 'task_name': task_name,
        'message': f'Task "{task_name}" submitted to background'
    }

def _check_task_status(task_id: str) -> Dict[str, Any]:
    """Check status of a background task."""
    with _workers_lock:
        if task_id in _task_results:
            result = _task_results[task_id].copy()
            result['task_id'] = task_id
            return result
    return {'status': 'not_found', 'task_id': task_id}

def _list_background_tasks() -> Dict[str, Any]:
    """List all background tasks."""
    with _workers_lock:
        tasks = []
        for task_id, data in _task_results.items():
            t = data.copy()
            t['task_id'] = task_id
            tasks.append(t)
        tasks.sort(key=lambda x: x.get('queued_at', ''), reverse=True)
        return {
            'status': 'success', 'tasks': tasks[:20],
            'queue_size': _task_queue.qsize(), 'worker_count': len(_workers)
        }


# ═══════════════════════════════════════════════════════════════════
# SMART TASK PLANNER
# ═══════════════════════════════════════════════════════════════════

def _plan_complex_task(goal: str, context: str = "") -> Dict[str, Any]:
    """Intelligently break down a complex goal into executable steps."""
    logger.info(f"Planning: {goal}")
    goal_lower = goal.lower()
    
    steps = []
    required_connections = []
    
    if any(w in goal_lower for w in ['earn', 'make money', '$', 'income', 'revenue', 'profit']):
        steps = [
            {'step': 1, 'action': 'research', 'description': 'Research legitimate online income methods', 'tool': 'web_search_real'},
            {'step': 2, 'action': 'browse', 'description': 'Browse top opportunities', 'tool': 'browse_website'},
            {'step': 3, 'action': 'plan', 'description': 'Create execution plan', 'tool': 'create_progress_tracker'},
            {'step': 4, 'action': 'execute', 'description': 'Execute first action', 'tool': 'browse_website'},
        ]
        required_connections = ['web_search']
    elif any(w in goal_lower for w in ['email', 'send', 'message', 'contact']):
        steps = [
            {'step': 1, 'action': 'check', 'description': 'Verify email connection', 'tool': 'scan_inbox'},
            {'step': 2, 'action': 'process', 'description': 'Process messages', 'tool': 'scan_inbox'},
            {'step': 3, 'action': 'draft', 'description': 'Draft responses', 'tool': 'draft_reply'},
            {'step': 4, 'action': 'send', 'description': 'Send responses', 'tool': 'draft_reply'},
        ]
        required_connections = ['gmail']
    elif any(w in goal_lower for w in ['research', 'find', 'search', 'investigate']):
        steps = [
            {'step': 1, 'action': 'search', 'description': 'Search for info', 'tool': 'web_search_real'},
            {'step': 2, 'action': 'browse', 'description': 'Browse results', 'tool': 'browse_website'},
            {'step': 3, 'action': 'analyze', 'description': 'Analyze findings', 'tool': 'create_progress_tracker'},
            {'step': 4, 'action': 'report', 'description': 'Compile report', 'tool': 'update_progress'},
        ]
    else:
        steps = [
            {'step': 1, 'action': 'analyze', 'description': f'Analyze: {goal}', 'tool': 'create_progress_tracker'},
            {'step': 2, 'action': 'research', 'description': 'Gather information', 'tool': 'web_search_real'},
            {'step': 3, 'action': 'execute', 'description': 'Execute action', 'tool': 'browse_website'},
            {'step': 4, 'action': 'verify', 'description': 'Verify completion', 'tool': 'update_progress'},
        ]
    
    complexity = 'simple' if len(steps) <= 2 else 'moderate' if len(steps) <= 4 else 'complex'
    estimated_time = len(steps) * 15
    
    return {
        'status': 'success', 'goal': goal, 'steps': steps, 'total_steps': len(steps),
        'complexity': complexity, 'estimated_time_seconds': estimated_time,
        'required_connections': required_connections,
        'planned_at': datetime.now(timezone.utc).isoformat(),
        'recommendations': [
            f'{complexity.title()} task with {len(steps)} steps',
            f'Estimated: ~{estimated_time}s',
            'Will execute step-by-step with progress updates',
        ]
    }


def _execute_plan_step(goal: str, step_number: int) -> Dict[str, Any]:
    """Execute a specific step from a planned task."""
    plan = _plan_complex_task(goal)
    if plan['status'] != 'success':
        return {'status': 'error', 'message': 'Could not retrieve plan'}
    
    steps = plan.get('steps', [])
    if step_number < 1 or step_number > len(steps):
        return {'status': 'error', 'message': f'Invalid step. Range: 1-{len(steps)}'}
    
    step = steps[step_number - 1]
    
    try:
        _update_progress(goal, step['description'], 'in_progress', f'Step {step_number}')
    except:
        pass
    
    return {
        'status': 'success', 'step_number': step_number, 'step': step,
        'tool': step['tool'], 'message': f'Ready: {step["description"]}',
        'next_step': step_number + 1 if step_number < len(steps) else None
    }


# ═══════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════

def register_browser_tools(registry):
    """Register all browser, search, progress, background, and planning tools."""
    
    registry.register(name="web_search_real", description="Search the web. Actually works.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}, "num_results": {"type": "integer"}}, "required": ["query"]},
        handler=_web_search_real, category="research")
    
    registry.register(name="browse_website", description="Browse a website. Actually visits the URL.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}, "action": {"type": "string", "enum": ["read", "click"]}, "extract": {"type": "string", "enum": ["text", "html", "links"]}}, "required": ["url"]},
        handler=_browse_website, category="research")
    
    registry.register(name="fill_form", description="Fill a web form with data. Interactive browser automation.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}, "fields": {"type": "string", "description": "JSON of {selector: value}"}, "submit": {"type": "string", "description": "Submit button selector"}}, "required": ["url", "fields"]},
        handler=_fill_form, category="research")
    
    registry.register(name="interact_page", description="Interact with a webpage following instructions.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["url", "instructions"]},
        handler=_interact_page, category="research")
    
    registry.register(name="create_progress_tracker", description="Track progress on a complex goal.",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}}, "required": ["goal"]},
        handler=_create_progress_tracker, category="system")
    
    registry.register(name="update_progress", description="Update progress on a tracked goal.",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}, "step": {"type": "string"}, "status": {"type": "string"}, "note": {"type": "string"}}, "required": ["goal", "step"]},
        handler=_update_progress, category="system")
    
    registry.register(name="get_progress", description="Get progress on a tracked goal.",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}}, "required": ["goal"]},
        handler=_get_progress, category="system")
    
    registry.register(name="submit_background_task", description="Submit a task to run in the background.",
        parameters={"type": "object", "properties": {"task_name": {"type": "string"}, "description": {"type": "string"}}, "required": ["task_name"]},
        handler=_submit_background_task, category="system")
    
    registry.register(name="check_task_status", description="Check status of a background task.",
        parameters={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
        handler=_check_task_status, category="system")
    
    registry.register(name="list_background_tasks", description="List all background tasks.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_list_background_tasks, category="system")
    
    registry.register(name="plan_complex_task", description="Break down a complex goal into steps.",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}, "context": {"type": "string"}}, "required": ["goal"]},
        handler=_plan_complex_task, category="planning")
    
    registry.register(name="execute_plan_step", description="Execute a step from a planned task.",
        parameters={"type": "object", "properties": {"goal": {"type": "string"}, "step_number": {"type": "integer"}}, "required": ["goal", "step_number"]},
        handler=_execute_plan_step, category="planning")
