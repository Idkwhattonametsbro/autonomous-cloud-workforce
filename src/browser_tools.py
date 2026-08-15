"""
Browser automation and real web search tools.
Actually browses websites and searches the web without needing API keys.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# Check if playwright is available
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Browser automation disabled.")


def _web_search_real(query: str, num_results: int = 5) -> Dict[str, Any]:
    """
    Actually search the web using DuckDuckGo HTML scraping.
    No API key needed.
    """
    logger.info(f"Real web search: {query}")
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # Use DuckDuckGo HTML version
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for result in soup.find_all('div', class_='result')[:num_results]:
            title_elem = result.find('a', class_='result__a')
            snippet_elem = result.find('a', class_='result__snippet')
            
            if title_elem:
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                
                results.append({
                    'title': title,
                    'url': link,
                    'snippet': snippet
                })
        
        return {
            'status': 'success',
            'query': query,
            'results': results,
            'result_count': len(results),
            'searched_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return {
            'status': 'error',
            'message': f'Web search failed: {str(e)}',
            'query': query
        }


def _browse_website(url: str, action: str = "read", extract: str = "text") -> Dict[str, Any]:
    """
    Browse a website and extract information.
    Uses Playwright for JavaScript-heavy sites, falls back to requests for simple pages.
    """
    logger.info(f"Browsing {url} (action: {action}, extract: {extract})")
    
    if PLAYWRIGHT_AVAILABLE:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                page.wait_for_load_state('networkidle')
                
                if extract == "text":
                    content = page.inner_text('body')
                elif extract == "html":
                    content = page.content()
                elif extract == "links":
                    links = page.eval_on_selector_all('a[href]', 'elements => elements.map(e => ({text: e.innerText, href: e.href}))')
                    content = json.dumps(links[:20])  # Limit to 20 links
                else:
                    content = page.inner_text('body')
                
                title = page.title()
                browser.close()
                
                return {
                    'status': 'success',
                    'url': url,
                    'title': title,
                    'content': content[:5000],  # Limit content size
                    'extract_type': extract,
                    'browsed_at': datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error(f"Playwright browsing failed: {e}")
            # Fall back to requests
            pass
    
    # Fallback to requests + BeautifulSoup
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        if extract == "text":
            content = soup.get_text(separator='\n', strip=True)
        elif extract == "html":
            content = str(soup)
        elif extract == "links":
            links = [{'text': a.get_text(strip=True), 'href': a.get('href', '')} 
                    for a in soup.find_all('a', href=True)[:20]]
            content = json.dumps(links)
        else:
            content = soup.get_text(separator='\n', strip=True)
        
        title = soup.title.string if soup.title else url
        
        return {
            'status': 'success',
            'url': url,
            'title': title,
            'content': content[:5000],
            'extract_type': extract,
            'browsed_at': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Web browsing failed: {e}")
        return {
            'status': 'error',
            'message': f'Failed to browse {url}: {str(e)}',
            'url': url
        }


def _create_progress_tracker(goal: str) -> Dict[str, Any]:
    """
    Create a progress tracking system for a goal.
    Stores progress in memory for persistence.
    """
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        
        progress = {
            'goal': goal,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'in_progress',
            'steps': [],
            'current_step': 0,
            'total_steps': 0,
            'notes': []
        }
        
        mem.remember(f'progress_{hash(goal) % 10000}', json.dumps(progress), 'progress_tracking')
        
        return {
            'status': 'success',
            'message': f'Progress tracking created for: {goal}',
            'goal': goal
        }
        
    except Exception as e:
        logger.error(f"Failed to create progress tracker: {e}")
        return {
            'status': 'error',
            'message': f'Failed to create progress tracker: {str(e)}'
        }


def _update_progress(goal: str, step: str, status: str = "completed", note: str = "") -> Dict[str, Any]:
    """
    Update progress on a tracked goal.
    """
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        
        progress_str = mem.recall(f'progress_{hash(goal) % 10000}', 'progress_tracking')
        if not progress_str:
            return {
                'status': 'error',
                'message': f'No progress tracker found for: {goal}'
            }
        
        progress = json.loads(progress_str)
        progress['steps'].append({
            'step': step,
            'status': status,
            'note': note,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        progress['current_step'] = len(progress['steps'])
        
        if note:
            progress['notes'].append(note)
        
        mem.remember(f'progress_{hash(goal) % 10000}', json.dumps(progress), 'progress_tracking')
        
        return {
            'status': 'success',
            'message': f'Progress updated: {step} ({status})',
            'current_step': progress['current_step'],
            'total_steps': len(progress['steps'])
        }
        
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")
        return {
            'status': 'error',
            'message': f'Failed to update progress: {str(e)}'
        }


def _get_progress(goal: str) -> Dict[str, Any]:
    """
    Get current progress on a tracked goal.
    """
    try:
        from dashboard.memory import MemoryStore
        mem = MemoryStore()
        
        progress_str = mem.recall(f'progress_{hash(goal) % 10000}', 'progress_tracking')
        if not progress_str:
            return {
                'status': 'not_found',
                'message': f'No progress tracker found for: {goal}'
            }
        
        progress = json.loads(progress_str)
        
        return {
            'status': 'success',
            'goal': progress['goal'],
            'current_step': progress['current_step'],
            'total_steps': len(progress['steps']),
            'steps': progress['steps'],
            'notes': progress['notes'],
            'created_at': progress['created_at']
        }
        
    except Exception as e:
        logger.error(f"Failed to get progress: {e}")
        return {
            'status': 'error',
            'message': f'Failed to get progress: {str(e)}'
        }


def register_browser_tools(registry):
    """Register browser automation and web tools."""
    
    registry.register(
        name="web_search_real",
        description="Search the web for information. Actually works without API keys.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results (default 5)"}
            },
            "required": ["query"]
        },
        handler=_web_search_real,
        category="research"
    )
    
    registry.register(
        name="browse_website",
        description="Browse a website and extract information. Actually visits the URL.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Website URL to browse"},
                "action": {"type": "string", "enum": ["read", "search", "interact"], "description": "What to do"},
                "extract": {"type": "string", "enum": ["text", "html", "links"], "description": "What to extract"}
            },
            "required": ["url"]
        },
        handler=_browse_website,
        category="research"
    )
    
    registry.register(
        name="create_progress_tracker",
        description="Create a progress tracker for a complex goal. Tracks steps and notes.",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The goal to track"}
            },
            "required": ["goal"]
        },
        handler=_create_progress_tracker,
        category="system"
    )
    
    registry.register(
        name="update_progress",
        description="Update progress on a tracked goal.",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The goal being tracked"},
                "step": {"type": "string", "description": "What step was completed"},
                "status": {"type": "string", "enum": ["completed", "in_progress", "failed"]},
                "note": {"type": "string", "description": "Additional notes"}
            },
            "required": ["goal", "step"]
        },
        handler=_update_progress,
        category="system"
    )
    
    registry.register(
        name="get_progress",
        description="Get current progress on a tracked goal.",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The goal to check progress on"}
            },
            "required": ["goal"]
        },
        handler=_get_progress,
        category="system"
    )
