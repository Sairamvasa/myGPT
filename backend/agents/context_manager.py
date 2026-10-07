"""Unified Context Manager for MyGPT.

Collects, ranks, deduplicates, scopes, and formats context from
conversation, memory, RAG, project, and tool sources before the
prompt builder assembles the final LLM prompt.

Design principles
-----------------
- Pure orchestration layer — does NOT replace rag.py, memory.py,
  memory_search.py, or prompt_builder.py.
- Retrieval is injected via callbacks so the module stays testable
  without external APIs or a live database.
- Every retrieved item is verified against the caller's user_id /
  project_id before it enters the bundle (defense in depth).
- Output is deterministic: stable sort keys, normalized dedup,
  capped per-source budgets.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("MyGPT.ContextManager")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextItem:
    source: str                       # "conversation" | "recent" | "project" | "rag" | "memory" | "tool"
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    conversation: list[ContextItem] = field(default_factory=list)
    recent: list[ContextItem] = field(default_factory=list)
    project: list[ContextItem] = field(default_factory=list)
    rag: list[ContextItem] = field(default_factory=list)
    memories: list[ContextItem] = field(default_factory=list)
    tool: list[ContextItem] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return sum(len(getattr(self, s)) for s in ("conversation", "recent", "project", "rag", "memories", "tool"))

    def all_items(self) -> list[ContextItem]:
        return (
            self.conversation
            + self.recent
            + self.project
            + self.rag
            + self.memories
            + self.tool
        )


# Deterministic priority: lower number = higher priority.
_SOURCE_PRIORITY = {
    "conversation": 0,
    "recent": 1,
    "project": 2,
    "rag": 3,
    "memory": 4,
    "tool": 5,
}

DEFAULT_BUDGET = {
    "conversation": 4000,
    "recent": 2000,
    "project": 3000,
    "rag": 6000,
    "memory": 2000,
    "tool": 3000,
    "_total": 14000,
}


# ---------------------------------------------------------------------------
# Security / isolation
# ---------------------------------------------------------------------------

def verify_scope(item: ContextItem, user_id: int, project_id: Optional[int] = None) -> bool:
    """Return True if *item* is scoped to the caller's user/project.

    Drops items whose metadata claims a different user_id or project_id.
    Items without scope metadata are accepted (backward-compatible).
    """
    meta = item.metadata or {}
    item_user = meta.get("user_id")
    item_project = meta.get("project_id")

    if item_user is not None and item_user != user_id:
        logger.warning("Scope drop: user_id mismatch %s != %s", item_user, user_id)
        return False

    if item_project is not None:
        if project_id is None or item_project != project_id:
            logger.warning("Scope drop: project_id mismatch %s != %s", item_project, project_id)
            return False

    return True


def _normalize_content(content: str) -> str:
    return " ".join(str(content).split())


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_context(items: list[ContextItem]) -> list[ContextItem]:
    """Sort items by source priority then score (desc), then deterministic tie-break."""

    def _key(item: ContextItem) -> tuple:
        src_priority = _SOURCE_PRIORITY.get(item.source, 99)
        norm = _normalize_content(item.content)
        tie_break = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        return (src_priority, -item.score, tie_break)

    return sorted(items, key=_key)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_context(items: list[ContextItem]) -> list[ContextItem]:
    """Remove items whose normalized content duplicates an earlier item.

    Keeps the first (highest-ranked) occurrence.
    """
    seen: set[str] = set()
    unique: list[ContextItem] = []
    for item in items:
        norm = _normalize_content(item.content)
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Limiting
# ---------------------------------------------------------------------------

def limit_context(
    bundle: ContextBundle,
    budget: Optional[dict[str, int]] = None,
) -> ContextBundle:
    """Cap each source and the total bundle to character budgets.

    Consumes highest-ranked items first within each source.
    """
    b = budget or DEFAULT_BUDGET
    total_budget = b.get("_total", DEFAULT_BUDGET["_total"])

    def _cap(items: list[ContextItem], source_budget: int) -> list[ContextItem]:
        kept: list[ContextItem] = []
        chars = 0
        for item in items:
            length = len(item.content)
            if chars + length <= source_budget:
                kept.append(item)
                chars += length
            else:
                break
        return kept

    conversation = _cap(bundle.conversation, b.get("conversation", DEFAULT_BUDGET["conversation"]))
    recent = _cap(bundle.recent, b.get("recent", DEFAULT_BUDGET["recent"]))
    project = _cap(bundle.project, b.get("project", DEFAULT_BUDGET["project"]))
    rag = _cap(bundle.rag, b.get("rag", DEFAULT_BUDGET["rag"]))
    memories = _cap(bundle.memories, b.get("memory", DEFAULT_BUDGET["memory"]))
    tool = _cap(bundle.tool, b.get("tool", DEFAULT_BUDGET["tool"]))

    # Total budget: drop lowest-priority items first.
    all_kept = (
        [(it, "conversation") for it in conversation]
        + [(it, "recent") for it in recent]
        + [(it, "project") for it in project]
        + [(it, "rag") for it in rag]
        + [(it, "memory") for it in memories]
        + [(it, "tool") for it in tool]
    )
    all_kept.sort(key=lambda pair: (_SOURCE_PRIORITY.get(pair[1], 99), -pair[0].score))

    total_chars = 0
    final: dict[str, list[ContextItem]] = {
        "conversation": [], "recent": [], "project": [],
        "rag": [], "memory": [], "tool": [],
    }
    for item, src in all_kept:
        length = len(item.content)
        if total_chars + length > total_budget:
            continue
        final[src].append(item)
        total_chars += length

    return ContextBundle(
        conversation=final["conversation"],
        recent=final["recent"],
        project=final["project"],
        rag=final["rag"],
        memories=final["memory"],
        tool=final["tool"],
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_context(bundle: ContextBundle) -> dict[str, Any]:
    """Produce deterministic structured output compatible with prompt_builder.

    Returns a dict with keys:
        context      – combined RAG + project text (str, for prompt_builder "context")
        memories     – list[str] (for prompt_builder "memories")
        history      – list[tuple[str, str]] (for prompt_builder "history")
        tool_results – str (for prompt_builder "tool_results")
        recent       – list[ContextItem] (exposed for caller use)
    """
    # RAG + project context merged, deterministic order (project first).
    parts: list[str] = []
    if bundle.project:
        parts.append("\n".join(it.content for it in bundle.project))
    if bundle.rag:
        parts.append("\n".join(it.content for it in bundle.rag))
    combined_context = "\n\n---\n\n".join(parts) if parts else ""

    history: list[tuple[str, str]] = []
    for it in bundle.conversation:
        role = it.metadata.get("role", "user")
        history.append((str(role), it.content))
    for it in bundle.recent:
        role = it.metadata.get("role", "user")
        history.append((str(role), it.content))

    memories = [it.content for it in bundle.memories]

    tool_results = "\n".join(it.content for it in bundle.tool) if bundle.tool else ""

    return {
        "context": combined_context,
        "memories": memories,
        "history": history,
        "tool_results": tool_results,
        "recent": list(bundle.recent),
    }


# ---------------------------------------------------------------------------
# High-level builder
# ---------------------------------------------------------------------------

def build_context(
    user_id: int,
    query: str,
    project_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    retrievers: Optional[dict[str, Callable[..., Any]]] = None,
    budget: Optional[dict[str, int]] = None,
) -> ContextBundle:
    """Collect, scope, rank, deduplicate, and limit context.

    Parameters
    ----------
    user_id: caller's user id (required for scope verification)
    query: the user's current request (used for relevance scoring)
    project_id: optional project scope
    chat_id: optional conversation scope
    retrievers: dict of source_name -> callable returning list[ContextItem].
        Defaults use lazy imports of the existing retrieval functions.
    budget: per-source character caps (see DEFAULT_BUDGET).

    Returns
    -------
    ContextBundle ready for format_context().
    """
    ret = retrievers or {}

    def _call(name: str, default: Any = None) -> Callable[..., Any]:
        if name in ret:
            return ret[name]
        if default is not None:
            return default
        raise ValueError(f"Retriever '{name}' not provided and no default available")

    # --- collect raw items ------------------------------------------------
    raw_conversation: list[ContextItem] = []
    raw_recent: list[ContextItem] = []
    raw_project: list[ContextItem] = []
    raw_rag: list[ContextItem] = []
    raw_memories: list[ContextItem] = []
    raw_tool: list[ContextItem] = []

    # Conversation history
    if chat_id is not None:
        try:
            from database import get_history
            history = get_history(chat_id)
            for role, message in history:
                raw_conversation.append(ContextItem(
                    source="conversation",
                    content=f"**{role}**: {message}",
                    score=1.0,
                    metadata={"role": role, "user_id": user_id, "chat_id": chat_id},
                ))
        except Exception as exc:
            logger.warning("ContextManager: conversation retrieval failed: %s", exc)

    # Recent context = last N conversation items (elevated priority)
    recent_count = 4
    for item in raw_conversation[-recent_count:]:
        raw_recent.append(ContextItem(
            source="recent",
            content=item.content,
            score=item.score + 0.5,
            metadata=dict(item.metadata),
        ))

    # Project context (injected retriever)
    try:
        project_retriever = ret.get("project")
        if project_retriever is not None:
            for content, meta in project_retriever(query, project_id, user_id):
                if verify_scope(ContextItem("project", content, metadata=meta or {}), user_id, project_id):
                    raw_project.append(ContextItem(
                        source="project", content=content, score=meta.get("score", 1.0) if meta else 1.0,
                        metadata=dict(meta or {}),
                    ))
    except Exception as exc:
        logger.warning("ContextManager: project retrieval failed: %s", exc)

    # RAG context (injected retriever)
    try:
        rag_retriever = ret.get("rag")
        if rag_retriever is not None:
            for content, meta in rag_retriever(query, user_id, project_id):
                if verify_scope(ContextItem("rag", content, metadata=meta or {}), user_id, project_id):
                    raw_rag.append(ContextItem(
                        source="rag", content=content, score=meta.get("score", 1.0) if meta else 1.0,
                        metadata=dict(meta or {}),
                    ))
    except Exception as exc:
        logger.warning("ContextManager: RAG retrieval failed: %s", exc)

    # Memory context (injected retriever)
    try:
        memory_retriever = ret.get("memory")
        if memory_retriever is not None:
            for content, meta in memory_retriever(query, user_id):
                if verify_scope(ContextItem("memory", content, metadata=meta or {}), user_id):
                    raw_memories.append(ContextItem(
                        source="memory", content=content, score=meta.get("score", 1.0) if meta else 1.0,
                        metadata=dict(meta or {}),
                    ))
    except Exception as exc:
        logger.warning("ContextManager: memory retrieval failed: %s", exc)

    # Tool results (injected retriever)
    try:
        tool_retriever = ret.get("tool")
        if tool_retriever is not None:
            for content, meta in tool_retriever(query, user_id, project_id):
                if verify_scope(ContextItem("tool", content, metadata=meta or {}), user_id, project_id):
                    raw_tool.append(ContextItem(
                        source="tool", content=content, score=meta.get("score", 0.5) if meta else 0.5,
                        metadata=dict(meta or {}),
                    ))
    except Exception as exc:
        logger.warning("ContextManager: tool retrieval failed: %s", exc)

    # --- pipeline ---------------------------------------------------------
    bundle = ContextBundle(
        conversation=raw_conversation,
        recent=raw_recent,
        project=raw_project,
        rag=raw_rag,
        memories=raw_memories,
        tool=raw_tool,
    )

    # Apply per-source ranking + dedup + limiting
    for src in ("conversation", "recent", "project", "rag", "memories", "tool"):
        items = getattr(bundle, src)
        ranked = rank_context(items)
        deduped = deduplicate_context(ranked)
        setattr(bundle, src, deduped)

    bundle = limit_context(bundle, budget)

    return bundle