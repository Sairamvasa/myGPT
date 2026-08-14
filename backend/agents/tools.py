import subprocess
import sys
import datetime
from ddgs import DDGS


def web_search(query: str, max_results: int = 5):
    """
    Search the web using DuckDuckGo to get up-to-date information, news, documentation, or facts.
    """
    results = []
    try:
        with DDGS() as ddgs:
            search_results = ddgs.text(
                query,
                max_results=max_results
            )
            for item in search_results:
                results.append({
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                    "link": item.get("href", "")
                })
    except Exception as e:
        print(f"Web search error: {e}")

    return results


def execute_python(code: str, timeout_seconds: int = 10) -> str:
    """
    Execute Python code in an isolated subprocess (Code Interpreter) to perform calculations,
    process data, test algorithms, or generate structured outputs.
    """
    try:
        process = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()

        if process.returncode != 0:
            return f"Code execution error (exit code {process.returncode}):\n{stderr or stdout}"

        if not stdout and not stderr:
            return "Code executed successfully (no output printed)."

        return stdout if stdout else f"Warnings/Errors:\n{stderr}"
    except subprocess.TimeoutExpired:
        return f"Execution timed out after {timeout_seconds} seconds."
    except Exception as e:
        return f"Execution error: {str(e)}"


def get_current_time() -> str:
    """
    Returns the exact current date, time, and day of the week.
    """
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y %I:%M:%S %p")