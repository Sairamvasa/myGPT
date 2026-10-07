"""Concrete tool implementations for the MyGPT agent.

Every implementation is a thin wrapper around an existing, already-tested
function so that behaviour is preserved exactly:

  python_exec   -> agents.tools.execute_python   (sandboxed, AST-validated)
  web_search    -> agents.tools.web_search         (DuckDuckGo + reformulation)
  get_current_time -> agents.tools.get_current_time
  rag_search    -> rag.search_project_pdf / rag.search_pdf (FAISS, scoped)
  vision        -> vision.analyze_image            (NVIDIA vision)
  image_gen     -> backend.gemini.generate_image   (Gemini image model)

Each executor has the signature ``(args: dict, context: ToolContext)
-> ToolResult`` and is responsible for converting the underlying function's
output into the standard :class:`~agents.tool_registry.ToolResult` contract.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from agents.tool_registry import (
    RiskLevel,
    Tool,
    ToolContext,
    ToolResult,
    ToolRegistry,
)

logger = logging.getLogger("MyGPT.Tools")


def _obs_block(tool_name: str, status: str, body: str) -> str:
    """Build a structured, clearly-delimited observation for the prompt."""
    return (
        f"<tool name=\"{tool_name}\">\n"
        f"<status>{status}</status>\n"
        f"<result>\n{body}\n</result>\n"
        f"</tool>"
    )


# ---------------------------------------------------------------------------
# python_exec
# ---------------------------------------------------------------------------

def _exec_python(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tool_registry import _sanitize_error
    from agents.tools import execute_python

    code: str = (args.get("code") or "").strip()
    timeout_seconds: int = args.get("timeout_seconds") or 10

    if not code:
        return ToolResult(
            tool_name="python_exec",
            success=False,
            error="No code provided.",
            observation=_obs_block(
                "python_exec", "error", "No code was provided to the code interpreter."
            ),
            metadata={"reason": "empty_code"},
        )

    try:
        raw = execute_python(code, timeout_seconds=timeout_seconds)
    except Exception as exc:  # pragma: no cover - defensive boundary
        safe = _sanitize_error(exc)
        logger.exception("python_exec tool failed")
        return ToolResult(
            tool_name="python_exec",
            success=False,
            error=safe,
            observation=_obs_block("python_exec", "error", f"Execution failed: {safe}"),
            metadata={"error_type": type(exc).__name__},
        )

    stdout = raw.get("stdout", "")
    stderr = raw.get("stderr", "")
    exit_code = raw.get("exit_code", -1)
    timed_out = bool(raw.get("timed_out", False))

    if raw.get("success"):
        observation = _obs_block(
            "python_exec", "success",
            f"Code executed successfully (exit_code={exit_code}).\nOutput:\n{stdout}",
        )
        return ToolResult(
            tool_name="python_exec",
            success=True,
            output=stdout,
            observation=observation,
            metadata={
                "exit_code": exit_code,
                "timed_out": timed_out,
                "code_length": len(code),
            },
            timed_out=timed_out,
        )

    err = raw.get("error") or stderr or "Code execution failed."
    status = "timeout" if timed_out else "error"
    return ToolResult(
        tool_name="python_exec",
        success=False,
        error=err,
        output=stdout,
        observation=_obs_block(
            "python_exec", status,
            f"Execution failed (exit_code={exit_code}).\nError:\n{err}",
        ),
        metadata={"exit_code": exit_code, "timed_out": timed_out},
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

def _exec_web_search(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tool_registry import _sanitize_error
    from agents.tools import web_search

    query: str = args.get("query") or ""
    max_results: int = int(args.get("max_results") or 5)

    if not query:
        return ToolResult(
            tool_name="web_search",
            success=False,
            error="No query provided.",
            observation=_obs_block("web_search", "error", "No search query was provided."),
        )

    try:
        result = web_search(query, max_results=max_results)
    except Exception as exc:  # pragma: no cover - defensive boundary
        safe = _sanitize_error(exc)
        logger.exception("web_search tool failed")
        return ToolResult(
            tool_name="web_search",
            success=False,
            error=safe,
            observation=_obs_block("web_search", "error", f"Web search failed: {safe}"),
            metadata={"error_type": type(exc).__name__},
        )
    returned = result.get("returned", 0)
    results = result.get("results", [])

    if not results:
        observation = _obs_block(
            "web_search", "no_results",
            "Web search returned no results.",
        )
        return ToolResult(
            tool_name="web_search",
            success=True,
            output="",
            observation=observation,
            metadata={
                "original_query": result.get("original_query"),
                "final_query": result.get("final_query"),
                "reformulated": result.get("reformulated"),
                "total_found": result.get("total_found", 0),
                "returned": returned,
            },
        )

    lines = []
    for item in results:
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "").strip()
        link = (item.get("link") or "").strip()
        if title or body or link:
            lines.append(f"Title: {title}\nSnippet: {body}\nSource: {link}")
    web_text = "\n\n".join(lines)

    header = (
        f"Retrieved {returned} search result(s) "
        f"(query: {result.get('final_query')!r}).\n\n"
    )
    observation = _obs_block("web_search", "success", header + web_text)

    return ToolResult(
        tool_name="web_search",
        success=True,
        output=web_text,
        observation=observation,
        metadata={
            "original_query": result.get("original_query"),
            "final_query": result.get("final_query"),
            "reformulated": result.get("reformulated"),
            "reformulation_reason": result.get("reformulation_reason"),
            "total_found": result.get("total_found", 0),
            "returned": returned,
        },
    )


# ---------------------------------------------------------------------------
# get_current_time
# ---------------------------------------------------------------------------

def _exec_get_time(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tools import get_current_time

    now = get_current_time()
    return ToolResult(
        tool_name="get_current_time",
        success=True,
        output=now,
        observation=_obs_block(
            "get_current_time", "success", f"System Real-Time Clock: {now}"
        ),
    )


# ---------------------------------------------------------------------------
# rag_search (project or user scoped, never cross-tenant)
# ---------------------------------------------------------------------------

def _exec_rag_search(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tool_registry import _sanitize_error
    from rag import search_pdf, search_project_pdf

    question: str = args.get("query") or ""

    if not question:
        return ToolResult(
            tool_name="rag_search",
            success=False,
            error="No query provided.",
            observation=_obs_block("rag_search", "error", "No search query was provided."),
        )

    try:
        if context.project_id is not None:
            context_str = search_project_pdf(question, context.project_id)
            scope = f"project:{context.project_id}"
        elif context.user_id is not None:
            context_str = search_pdf(question, context.user_id)
            scope = f"user:{context.user_id}"
        else:
            context_str = None
            scope = "none"
    except Exception as exc:
        safe = _sanitize_error(exc)
        logger.exception("rag_search tool failed")
        return ToolResult(
            tool_name="rag_search",
            success=False,
            error=safe,
            observation=_obs_block("rag_search", "error", f"Document retrieval failed: {safe}"),
            metadata={"error_type": type(exc).__name__, "scope": "none"},
        )

    if context_str:
        return ToolResult(
            tool_name="rag_search",
            success=True,
            output=context_str,
            observation=_obs_block(
                "rag_search", "success",
                f"Document context retrieved (scope={scope}).\n\n{context_str}",
            ),
            metadata={"scope": scope, "user_id": context.user_id,
                      "project_id": context.project_id},
        )

    return ToolResult(
        tool_name="rag_search",
        success=True,
        output="",
        observation=_obs_block(
            "rag_search", "no_results",
            f"No relevant document context found (scope={scope}). "
            "The vector index is empty or no chunk passed the relevance "
            "threshold.",
        ),
        metadata={"scope": scope, "user_id": context.user_id,
                  "project_id": context.project_id},
    )


# ---------------------------------------------------------------------------
# vision
# ---------------------------------------------------------------------------

def _exec_vision(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tool_registry import _sanitize_error

    image_path = args.get("image_path") or ""
    prompt = args.get("prompt") or "Describe this image."

    if not image_path:
        return ToolResult(
            tool_name="vision",
            success=False,
            error="No image_path provided.",
            observation=_obs_block(
                "vision",
                "error",
                "No image path was provided.",
            ),
        )

    try:
        from vision import analyze_image
        answer = analyze_image(image_path, prompt)
    except Exception as exc:
        safe = _sanitize_error(exc)
        logger.exception("vision tool failed")
        return ToolResult(
            tool_name="vision",
            success=False,
            error=safe,
            observation=_obs_block("vision", "error", f"Image analysis failed: {safe}"),
            metadata={"error_type": type(exc).__name__},
        )

    return ToolResult(
        tool_name="vision",
        success=True,
        output=answer,
        observation=_obs_block(
            "vision",
            "success",
            f"Image analysis (prompt={prompt!r}):\n\n{answer}",
        ),
    )


# ---------------------------------------------------------------------------
# image_gen (requires confirmation — generative / billed action)
# ---------------------------------------------------------------------------

def _exec_image_gen(args: Dict[str, Any], context: ToolContext) -> ToolResult:
    from agents.tool_registry import _sanitize_error

    prompt: str = args.get("prompt") or ""
    aspect_ratio: str = args.get("aspect_ratio") or "1:1"

    if not prompt:
        return ToolResult(
            tool_name="image_gen",
            success=False,
            error="No prompt provided.",
            observation=_obs_block(
                "image_gen", "error", "No prompt was provided for image generation."
            ),
        )

    try:
        from gemini import generate_image
    except ImportError as exc:  # pragma: no cover - environment dependent
        return ToolResult(
            tool_name="image_gen",
            success=False,
            error=f"Image generation is unavailable: {exc}",
            observation=_obs_block(
                "image_gen", "error",
                "Image generation dependencies are not installed.",
            ),
        )

    try:
        image_b64 = generate_image(prompt, aspect_ratio)
    except Exception as exc:
        safe = _sanitize_error(exc)
        logger.exception("image_gen tool failed")
        return ToolResult(
            tool_name="image_gen",
            success=False,
            error=safe,
            observation=_obs_block("image_gen", "error", f"Image generation failed: {safe}"),
            metadata={"error_type": type(exc).__name__},
        )
    result_md = f"![Generated Image](data:image/png;base64,{image_b64})"
    return ToolResult(
        tool_name="image_gen",
        success=True,
        output=result_md,
        observation=_obs_block(
            "image_gen", "success",
            f"Image generated for prompt: {prompt}",
        ),
        metadata={"aspect_ratio": aspect_ratio},
    )


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------




def _web_search_tool() -> Tool:
    return Tool(
        name="web_search",
        description="Search the web via DuckDuckGo with query reformulation and domain quality filtering.",
        category="retrieval",
        input_schema={
            "query": {"type": "string", "description": "Search query.", "required": True},
            "max_results": {"type": "integer", "description": "Max results to return.", "required": False},
        },
        requires_confirmation=False,
        risk_level=RiskLevel.MEDIUM,
        timeout_seconds=15,
        executor=_exec_web_search,
    )


def _get_time_tool() -> Tool:
    return Tool(
        name="get_current_time",
        description="Return the server's current date, time, and day of the week.",
        category="time",
        input_schema={},
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=5,
        executor=_exec_get_time,
    )


def _rag_search_tool() -> Tool:
    return Tool(
        name="rag_search",
        description=(
            "Retrieve relevant chunks from the user's or project's uploaded "
            "documents (FAISS, relevance-thresholded)."
        ),
        category="retrieval",
        input_schema={
            "query": {"type": "string", "description": "Question to search documents for.", "required": True},
        },
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=20,
        executor=_exec_rag_search,
    )


def _python_tool() -> Tool:
    # requires_confirmation=False: the AST sandbox (no imports, blocked
    # names, subprocess timeout, stripped env) already neutralises the danger,
    # so a math/word-problem turn returns a direct answer without an extra
    # approval round-trip (preserving the existing Agent contract).
    return Tool(
        name="python_exec",
        description=(
            "Execute safe Python code in a sandboxed subprocess. "
            "No imports, no filesystem/network access, no dangerous builtins."
        ),
        category="runtime",
        input_schema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Execution timeout in seconds.",
                },
            },
            "required": ["code"],
        },
        requires_confirmation=False,
        risk_level=RiskLevel.HIGH,
        timeout_seconds=30,
        executor=_exec_python,
    )
    
def _vision_tool() -> Tool:
    return Tool(
        name="vision",
        description="Analyze an image file and return a text description.",
        category="runtime",
        input_schema={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the image file.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Instruction for the vision model.",
                },
            },
            "required": ["image_path"],
        },
        requires_confirmation=False,
        risk_level=RiskLevel.MEDIUM,
        timeout_seconds=60,
        executor=_exec_vision,
    )

def _image_gen_tool() -> Tool:
    return Tool(
        name="image_gen",
        description="Generate an image from a text prompt using the Gemini image model.",
        category="runtime",
        input_schema={
            "prompt": {"type": "string", "description": "Text description of the image.", "required": True},
            "aspect_ratio": {"type": "string", "description": "Aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4).", "required": False},
        },
        requires_confirmation=True,
        risk_level=RiskLevel.HIGH,
        timeout_seconds=120,
        executor=_exec_image_gen,
    )


_DEFAULT_BUILDERS = [
    _python_tool,
    _web_search_tool,
    _get_time_tool,
    _rag_search_tool,
    _vision_tool,
    _image_gen_tool,
]


def register_default_tools(registry: ToolRegistry) -> ToolRegistry:
    """Register the full set of default MyGPT tools."""

    for builder in _DEFAULT_BUILDERS:
        registry.register(builder())

    logger.info("Registered %d default tools: %s",
                len(_DEFAULT_BUILDERS), registry.names())
    return registry


_SHARED_REGISTRY: "ToolRegistry | None" = None


def get_tool_registry() -> ToolRegistry:
    """Return a shared registry populated with default tools."""

    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = register_default_tools(ToolRegistry())
    return _SHARED_REGISTRY


def reset_tool_registry() -> None:
    """Drop the shared registry — used by tests."""

    global _SHARED_REGISTRY
    _SHARED_REGISTRY = None
