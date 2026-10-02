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



# ---------------------------------------------------------------------------
# Code execution security
# ---------------------------------------------------------------------------

# Modules that must never be importable in user code.
_BLOCKED_IMPORTS: frozenset = frozenset({
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources",
    "signal", "resource", "gc", "weakref",
    "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
    "__main__", "__future__", "__builtin__",
    "pathlib", "shutil", "requests",
})

# Built-in names/identifiers that must not appear in user code.
_BLOCKED_NAMES: frozenset = frozenset({
    "__import__", "breakpoint", "compile", "eval", "exec",
    "getattr", "globals", "input", "locals", "open", "setattr", "vars",
    "exit", "quit", "help", "license", "copyright", "credits",
    # module names that must not be reachable as bare names either
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources",
    "pathlib", "shutil", "requests",
})

MAX_CODE_CHARS = 12_000
MAX_OUTPUT_CHARS = 64_000


def _validate_python(code: str) -> List[str]:
    """
    Authoritative Python safety validator (single definition — Bug 2 fix).

    Walks the AST and returns a list of human-readable error strings for
    any blocked import, blocked name usage, dunder-attribute access, or
    blocked built-in call.  Returns an empty list if the code is safe.

    Security rules enforced:
      No imports from _BLOCKED_IMPORTS (filesystem, network, process ...)
      No direct use of names in _BLOCKED_NAMES
      No access to dunder (__xx__) attributes
      No calls to dangerous built-ins (eval, exec, open, __import__ ...)
    """
    errors: List[str] = []

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"Syntax error: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    errors.append(f"Import of '{alias.name}' is not allowed")

        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _BLOCKED_IMPORTS:
                errors.append(f"Import from '{node.module}' is not allowed")

        elif isinstance(node, ast.Name):
            if node.id in _BLOCKED_NAMES:
                errors.append(f"Use of '{node.id}' is not allowed")

        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                errors.append(
                    f"Access to dunder attribute '{node.attr}' is not allowed"
                )

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in _BLOCKED_NAMES:
                    errors.append(f"Call to '{node.func.id}' is not allowed")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in _BLOCKED_NAMES:
                    errors.append(f"Call to '{node.func.attr}' is not allowed")

    return errors


def _indent_code(code: str, indent: int) -> str:
    """Indent every non-empty line by *indent* spaces."""
    lines = code.splitlines()
    indented = []
    for line in lines:
        if line.strip() == "":
            indented.append("")
        else:
            indented.append(" " * indent + line)
    return "\n".join(indented)


def execute_python(code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed subprocess with safety controls.

    Security design (Bug 4 fix)
    ---------------------------
    BEFORE this fix the wrapper injected 'import sys' and 'import io' at the
    top of the executed script, making both names available to user code even
    though the AST validator would have rejected 'import sys' in user code.
    subprocess.run(capture_output=True) already captures stdout/stderr at the
    OS level, so the in-process StringIO redirect was both unnecessary AND
    a security hole.

    After this fix:
      1. The wrapper does NOT import sys or io -- those names are absent from
         the executed script's namespace.
      2. stdout/stderr are captured by subprocess.run(capture_output=True).
      3. The wrapper only wraps user code in try/except so tracebacks appear
         in stderr rather than being lost.
      4. Subprocess runs with -I (isolated) mode and a stripped environment
         (no PYTHONPATH, no API keys, no .env values).

    Returns a dict with:
      success   - bool
      stdout    - str
      stderr    - str
      exit_code - int
      timed_out - bool
      error     - str | None
    """
    if len(code) > MAX_CODE_CHARS:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                f"Code rejected: maximum allowed size is {MAX_CODE_CHARS} characters."
            ),
            "exit_code": -1,
            "timed_out": False,
            "error": f"Code exceeds maximum length of {MAX_CODE_CHARS} characters",
        }

    # Validate safety before executing anything.
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

    # SECURITY: do NOT import sys or io here -- that would put them in scope
    # for user code.  subprocess.run(capture_output=True) handles I/O capture
    # at the OS level so no in-process redirect is needed.
    wrapped_code = (
        "try:\n"
        + _indent_code(code, 4)
        + "\nexcept Exception:\n"
        + "    import traceback as _mygpt_tb\n"
        + "    _mygpt_tb.print_exc()\n"
        + "    raise SystemExit(1)\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(wrapped_code)
        temp_file = fh.name

    try:
        # Stripped environment: no PYTHONPATH, no API keys, no secrets.
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
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "timed_out": False,
            "error": str(exc),
        }
    finally:
        try:
            os.unlink(temp_file)
        except OSError:
            pass



def get_current_time() -> str:
    """
    Returns the exact current date, time, and day of the week.
    """
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y %I:%M:%S %p")
