"""
Response grounding and verification utilities for MyGPT.

Centralised here so both the text-chat path (app.py) and the
voice-chat path (voice_agent/agent.py) apply identical post-LLM
verification without creating a circular import dependency.

Grounding rules:
- current_info / web_research answers must have numeric values that
  are directly present in the search-tool results.
- If the answer makes a freshness claim but the value cannot be
  verified against retrieved results, return a safe refusal.
- RAG grounding is handled by agents.rag_verifier; this module only
  deals with live-search grounding.
"""

import re
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger("MyGPT.Grounding")

# ---------------------------------------------------------------------------
# Regex: extract currency / unit-bearing numbers from text.
# Used to cross-check LLM answer values against retrieved search snippets.
# ---------------------------------------------------------------------------
_CURRENT_INFO_VALUE_RE = re.compile(
    r"(?P<prefix>\u20b9|rs\.?|inr|\$|usd|eur|gbp|\u20ac|\u00a3)?\s*"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<suffix>%|(?:/|per\s+)?(?:litre|liter|gallon|kg|gram|ounce|oz|barrel|unit|share|coin|btc|eth|bitcoin|rupees?|dollars?|celsius|fahrenheit|degrees?))?",
    re.IGNORECASE,
)


def _normalize_grounding_number(value: str) -> str | None:
    """Normalise a number string to a canonical decimal string, or None on failure."""
    try:
        number = Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return format(number.normalize(), "f")


def _extract_current_info_values(text: str | None) -> set[str]:
    """Return the set of canonical numeric values that carry a currency/unit marker."""
    if not text:
        return set()

    values: set[str] = set()
    for match in _CURRENT_INFO_VALUE_RE.finditer(text):
        if not (match.group("prefix") or match.group("suffix")):
            continue
        normalized = _normalize_grounding_number(match.group("number"))
        if normalized is not None:
            values.add(normalized)
    return values


def _fallback_current_info_answer(tool_results: str | None) -> str:
    """Build a minimal safe answer from raw search results, or a generic refusal."""
    if not tool_results or "returned no results" in tool_results.lower():
        return "I couldn't verify the current information."

    value_lines = [
        line.strip().strip("*")
        for line in tool_results.splitlines()
        if any(
            match.group("prefix") or match.group("suffix")
            for match in _CURRENT_INFO_VALUE_RE.finditer(line)
        )
    ]
    source_match = re.search(r"Source:\s*(\S+)", tool_results)
    source = source_match.group(1) if source_match else None

    if value_lines:
        answer = f"Based on the retrieved search result: {value_lines[0]}"
        if source:
            answer += f" [Source: {source}]"
        return answer

    return "I couldn't verify the current information."


def _enforce_current_info_grounding(answer: str, tool_results: str | None) -> str:
    """
    Validate that the LLM answer is grounded in the retrieved search results.

    - If no search results were retrieved, return a safe refusal.
    - If the answer makes a freshness claim but no verifiable value is present
      in the results, return a safe refusal.
    - If all claimed values are present in results, return the answer unchanged.
    - Otherwise fall back to a minimal answer derived from results.
    """
    if (
        not tool_results
        or "could not be verified" in tool_results.lower()
        or "no results" in tool_results.lower()
    ):
        return "I couldn't verify the current information from a live search."

    stripped_answer = answer.strip()
    if not stripped_answer or stripped_answer.endswith((":", "-", "—", "...")):
        return _fallback_current_info_answer(tool_results)

    answer_values = _extract_current_info_values(answer)
    source_values = _extract_current_info_values(tool_results)

    if not answer_values:
        if not source_values:
            return answer
        # Answer has no verifiable numeric value but results do —
        # reject freshness claims that can't be grounded.
        freshness_claim = re.search(
            r"\b(?:today|current|latest|now|live|as of)\b",
            answer,
            re.IGNORECASE,
        )
        return (
            "I couldn't verify the current information from the retrieved "
            "search results."
            if freshness_claim
            else answer
        )

    if answer_values.issubset(source_values):
        # Values are present in results — also verify any explicit dates.
        claimed_dates = set(
            re.findall(
                r"\b(?:January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                answer,
                re.IGNORECASE,
            )
        )
        if claimed_dates and not claimed_dates.issubset(
            set(
                re.findall(
                    r"\b(?:January|February|March|April|May|June|July|August|"
                    r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                    tool_results,
                    re.IGNORECASE,
                )
            )
        ):
            return "I couldn't verify the date associated with the current information."
        return answer

    return _fallback_current_info_answer(tool_results)
