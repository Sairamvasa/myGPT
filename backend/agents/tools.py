import ast
import subprocess
import sys
import datetime
import re
import tempfile
import os
from typing import Optional, Dict, Any, List
from ddgs import DDGS

# --- Query reformulation rules (deterministic, rule-based) ---

# Contradictory geography: "capital of X in Y" where the premise may be wrong.
# Extract the country and drop the contradictory continent clause.
_GEO_CONTRADICTION = re.compile(
    r"(capital\s+(?:of\s+)?(.+?)\s+in\s+(asia|europe|africa|"
    r"north\s+america|south\s+america|australia|antarctica))",
    re.IGNORECASE
)

# Planet ambiguity: distinguish planets from other entities.
# If a planet name appears in a "who is the X of Y" question where X is a 
# leadership title, disambiguate toward the planet.
_PLANET_AMBIGUATION = re.compile(
    r"\b(who\s+is\s+the\s+(?:president|prime\s+minister|leader|ruler|king|queen|emperor|chancellor|premier|governor|mayor)\s+of\s+(?:the\s+)?)(mercury|venus|mars|jupiter|saturn|uranus|neptune|pluto|moon|sun)(?=\b|\?|\.|!|,|;|$)",
    re.IGNORECASE
)

_PLANET_COMPANY_MARKERS = re.compile(
    r"\b(incorporated|inc\b|company|corp\b|corporation|llc|ltd\b|enterprises|industries|group|holdings)\b",
    re.IGNORECASE
)

# Mars ambiguity: distinguish the planet from Mars Incorporated.
# If "Mars" appears without explicit company markers (e.g. "Mars Inc"),
# disambiguate toward the planet.
_MARS_AMBIGUATION = re.compile(r"\b(who\s+is\s+the\s+(?:president|ceo|ceo\s+of|leader\s+of)\s+)(mars)(?=\b|\?|\.|!|,|;|$)", re.IGNORECASE)

_MARS_COMPANY_MARKERS = re.compile(
    r"\b(mars\s+incorporated|mars\s+inc\b|mars\s+company|mars\s+corp\b|mars\s+incorporated|mars\s+wrigley|mars\s+petcare)\b",
    re.IGNORECASE
)

# False premise patterns: "what is X in Y" where Y contradicts X's location
_FALSE_PREMISE_PATTERNS = [
    # "What is the capital of France in Asia?" -> "capital of France"
    re.compile(r"what\s+is\s+the\s+(capital|capital\s+city)\s+of\s+(.+?)\s+in\s+(asia|europe|africa|north\s+america|south\s+america|australia|antarctica)\b", re.IGNORECASE),
    # "Which city is the capital of France in Asia?" -> "capital of France"
    re.compile(r"which\s+(city|town)\s+is\s+the\s+(capital|capital\s+city)\s+of\s+(.+?)\s+in\s+(asia|europe|africa|north\s+america|south\s+america|australia|antarctica)\b", re.IGNORECASE),
    # "Where is the capital of France in Asia?" -> "capital of France"
    re.compile(r"where\s+is\s+the\s+(capital|capital\s+city)\s+of\s+(.+?)\s+in\s+(asia|europe|africa|north\s+america|south\s+america|australia|antarctica)\b", re.IGNORECASE),
]

# Low-authority domains that are unlikely to provide factual answers.
_LOW_QUALITY_DOMAINS = {
    "tiktok.com", "youtube.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "reddit.com", "pinterest.com",
    "tumblr.com", "snapchat.com", "linkedin.com", "quora.com",
    "amazon.com", "ebay.com", "etsy.com", "walmart.com",
}

# High-authority domains for factual queries
_HIGH_AUTHORITY_DOMAINS = {
    "wikipedia.org", "britannica.com", "cia.gov", "worldbank.org",
    "un.org", "who.int", "nasa.gov", "noaa.gov", "nih.gov",
    "cdc.gov", "fda.gov", "epa.gov", "energy.gov", "state.gov",
    "whitehouse.gov", "parliament.uk", "europa.eu", "oecd.org",
    "imf.org", "bis.org", "reuters.com", "apnews.com", "bbc.com",
    "npr.org", "pbs.org", "nytimes.com", "washingtonpost.com",
    "wsj.com", "ft.com", "economist.com", "nature.com", "science.org",
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nih.gov", "cdc.gov",
}


def _reformulate_query(query: str):
    """
    Deterministic, rule-based query reformulation.

    Returns (final_query, was_reformulated, reason).
    """
    original_query = query
    
    # 1. Contradictory geography: drop the continent clause
    geo_match = _GEO_CONTRADICTION.search(query)
    if geo_match:
        country = geo_match.group(2).strip()
        return f"capital of {country}", True, "dropped contradictory continent clause"

    # 2. False premise patterns: "what is the capital of X in Y" where Y contradicts X
    for pattern in _FALSE_PREMISE_PATTERNS:
        match = pattern.search(query)
        if match:
            # Extract the entity (country/city) that the question is actually about
            # Group 2 or 3 depending on pattern
            entity = match.group(2) if match.lastindex >= 2 else match.group(3) if match.lastindex >= 3 else None
            if entity:
                entity = entity.strip()
                # Determine the question type
                if "capital" in query.lower():
                    return f"capital of {entity}", True, "dropped contradictory continent clause from false premise"
                return f"{entity}", True, "dropped contradictory location clause from false premise"

    # 3. Planet ambiguity: distinguish planets from other entities
    planet_match = _PLANET_AMBIGUATION.search(query)
    if planet_match:
        prefix = planet_match.group(1)
        planet = planet_match.group(2).strip().capitalize()
        return f"{prefix}planet {planet}", True, f"disambiguated {planet.lower()} to planet"

    # 3b. Mars ambiguity: distinguish the planet from Mars Incorporated
    mars_match = _MARS_AMBIGUATION.search(query)
    if mars_match and not _MARS_COMPANY_MARKERS.search(query):
        prefix = mars_match.group(1)
        return f"{prefix}planet Mars", True, "disambiguated Mars to planet Mars"

    return query, False, None


def _score_result(item, query_terms):
    """
    Score a search result by keyword overlap with the query.
    Returns a score >= 0. Higher is better.
    """
    title = (item.get("title") or "").lower()
    body = (item.get("body") or "").lower()
    domain = (item.get("href") or "").lower()

    score = 0
    for term in query_terms:
        if term in title:
            score += 3
        if term in body:
            score += 1
        if term in domain:
            score -= 2  # penalize keyword-stuffed domains

    # Penalize low-quality domains
    for bad_domain in _LOW_QUALITY_DOMAINS:
        if bad_domain in domain:
            score -= 5

    # Boost high-authority domains for factual queries
    for auth_domain in _HIGH_AUTHORITY_DOMAINS:
        if auth_domain in domain:
            score += 3

    return score


def _filter_and_rank_results(results, query, min_score=1):
    """Filter out low-quality results and rank by relevance."""
    query_terms = [
        word.lower() for word in query.split()
        if len(word) > 2 and word.lower() not in {
            "the", "and", "for", "are", "was", "what", "how", "who",
            "where", "when", "why", "that", "this", "with", "from",
            "have", "will", "your", "about", "their", "there", "they",
            "after", "before", "between", "among"
        }
    ]

    scored = []
    for item in results:
        score = _score_result(item, query_terms)
        if score >= min_score:
            scored.append((score, item))

    # Sort by score descending, keep original order for ties
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored]


def web_search(query: str, max_results: int = 5):
    """
    Search the web using DuckDuckGo to get up-to-date information, news,
    documentation, or facts.

    Returns a dict with:
      - results: list of {title, body, link}
      - original_query: the query as received
      - final_query: the query actually sent to DuckDuckGo
      - reformulated: whether the query was changed
      - reformulation_reason: explanation if reformulated
      - total_found: raw results before filtering
      - returned: results after filtering
    """
    original_query = query
    final_query, reformulated, reason = _reformulate_query(query)

    results = []
    total_found = 0

    try:
        with DDGS(timeout=8) as ddgs:
            search_results = list(ddgs.text(final_query, max_results=max_results))
            total_found = len(search_results)

            for item in search_results:
                results.append({
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                    "link": item.get("href", ""),
                    "domain": item.get("href", "").split("/")[2] if item.get("href") else "",
                })

            # Phase 1: filter and rank
            if results:
                results = _filter_and_rank_results(results, final_query)

            # Phase 2: fallback if filtered results are empty
            if not results and reformulated:
                # Try the original query as fallback
                fallback_results = []
                for item in ddgs.text(original_query, max_results=max_results):
                    fallback_results.append({
                        "title": item.get("title", ""),
                        "body": item.get("body", ""),
                        "link": item.get("href", ""),
                        "domain": item.get("href", "").split("/")[2] if item.get("href") else "",
                    })
                if fallback_results:
                    fallback_results = _filter_and_rank_results(
                        fallback_results, original_query
                    )
                    results = fallback_results
                    final_query = original_query
                    reformulated = False
                    reason = None

    except Exception as e:
        print(f"Web search error: {e}")

    return {
        "results": results,
        "original_query": original_query,
        "final_query": final_query,
        "reformulated": reformulated,
        "reformulation_reason": reason,
        "total_found": total_found,
        "returned": len(results),
    }


_BLOCKED_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
MAX_CODE_CHARS = 12_000
MAX_OUTPUT_CHARS = 64_000


def _validate_python(code: str) -> List[str]:
    """Validate Python code for safety violations."""
    BLOCKED_IMPORTS = {
        "sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
        "ctypes", "subprocess", "signal", "resource", "gc", "weakref",
        "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
        "__main__", "__future__", "__builtin__", "builtins",
    }

    BLOCKED_NAMES = {
        "__import__", "breakpoint", "compile", "eval", "exec", "getattr",
        "globals", "input", "locals", "open", "setattr", "vars",
        "exit", "quit", "help", "license", "copyright", "credits",
        "sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
    }

    errors = []

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.split('.')[0] in {"sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
        "ctypes", "subprocess", "signal", "resource", "gc", "weakref",
        "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
        "__main__", "__future__", "__builtin__", "builtins"}:
                    errors.append(f"Import of '{alias.name}' is not allowed")

        if isinstance(node, ast.Name):
            if node.id in {"__import__", "eval", "exec", "compile", "open", "input", "getattr", "setattr", "globals", "locals", "vars", "breakpoint", "exit", "quit", "help", "license", "copyright", "credits"}:
                errors.append(f"Access to '{node.id}' is not allowed")

        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            errors.append(f"Access to dunder attribute '{node.attr}' is not allowed")

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "open", "input", "__import__", "getattr", "setattr", "globals", "locals", "vars"}:
                errors.append(f"Calling '{node.func.id}' is not allowed")

    return errors


def execute_python(code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed subprocess with safety controls.

    Returns a dict with:
    - success: bool
    - stdout: str
    - stderr: str
    - exit_code: int
    - timed_out: bool
    - error: str (if any)
    """
    MAX_CODE_CHARS = 12_000
    MAX_OUTPUT_CHARS = 64_000

    if len(code) > MAX_CODE_CHARS:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Code rejected for safety: maximum code size is {MAX_CODE_CHARS} characters.",
            "exit_code": -1,
            "timed_out": False,
            "error": f"Code exceeds maximum length of {MAX_CODE_CHARS} characters",
        }

    # Validate code for safety
    safety_errors = _validate_python(code)
    if safety_errors:
        return {
            "success": False,
            "stdout": "",
            "stderr": "\n".join(safety_errors),
            "exit_code": -1,
            "timed_out": False,
            "error": "Safety validation failed: " + "; ".join(safety_errors),
        }

    timeout_seconds = min(max(int(timeout_seconds), 1), 30)

    # Prepare the code for execution with stdout/stderr capture
    wrapped_code = f"""
import sys
import io

# Capture stdout/stderr
_stdout = io.StringIO()
_stderr = io.StringIO()
_old_stdout = sys.stdout
_old_stderr = sys.stderr
sys.stdout = _stdout
sys.stderr = _stderr

try:
{_indent_code(code, 8)}
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    sys.stdout = _old_stdout
    sys.stderr = _old_stderr
    print(_stdout.getvalue(), end='', file=sys.__stdout__)
    print(_stderr.getvalue(), end='', file=sys.__stderr__)
"""

    # Use a temporary file for execution
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(wrapped_code)
        temp_file = f.name

    try:
        env = {
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", ""),
        }

        proc = subprocess.run(
            [sys.executable, "-I", "-B", temp_file],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            cwd=tempfile.gettempdir(),
        )

        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode

        MAX_OUTPUT_CHARS = 64_000
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = stdout[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = stderr[:MAX_OUTPUT_CHARS] + "\n[stderr truncated]"

        return {
            "success": exit_code == 0,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exit_code": exit_code,
            "timed_out": False,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds",
            "exit_code": -1,
            "timed_out": True,
            "error": f"Execution timed out after {timeout_seconds} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "timed_out": False,
            "error": str(e),
        }
    finally:
        try:
            os.unlink(temp_file)
        except OSError:
            pass


def _indent_code(code: str, indent: int) -> str:
    """Indent each line of code by the specified amount."""
    lines = code.splitlines()
    indented = []
    for line in lines:
        if line.strip() == "":
            indented.append("")
        else:
            indented.append(" " * indent + line)
    return "\n".join(indented)


def _validate_python(code: str) -> List[str]:
    """Validate Python code for safety violations."""
    BLOCKED_IMPORTS = {
        "sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
        "ctypes", "subprocess", "signal", "resource", "gc", "weakref",
        "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
        "__main__", "__future__", "__builtin__", "builtins",
    }

    BLOCKED_NAMES = {
        "__import__", "breakpoint", "compile", "eval", "exec", "getattr",
        "globals", "input", "locals", "open", "setattr", "vars",
        "exit", "quit", "help", "license", "copyright", "credits",
        "sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
    }

    errors = []

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.split('.')[0] in {"sys", "os", "subprocess", "threading", "multiprocessing",
        "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
        "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
        "mmap", "platform", "sysconfig", "site", "importlib",
        "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
        "ctypes", "subprocess", "signal", "resource", "gc", "weakref",
        "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
        "__main__", "__future__", "__builtin__", "builtins"}:
                    errors.append(f"Import of '{alias.name}' is not allowed")

        if isinstance(node, ast.Name):
            if node.id in {"__import__", "eval", "exec", "compile", "open", "input", "getattr", "setattr", "globals", "locals", "vars", "breakpoint", "exit", "quit", "help", "license", "copyright", "credits"}:
                errors.append(f"Access to '{node.id}' is not allowed")

        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            errors.append(f"Access to dunder attribute '{node.attr}' is not allowed")

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "open", "input", "__import__", "getattr", "setattr", "globals", "locals", "vars"}:
                errors.append(f"Calling '{node.func.id}' is not allowed")

    return errors


def get_current_time() -> str:
    """
    Returns the exact current date, time, and day of the week.
    """
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y %I:%M:%S %p")
