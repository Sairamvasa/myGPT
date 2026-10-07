import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MemoryCandidate:
    fact: str
    category: str
    key: str
    importance: int = 3


# Categories used by the production memory layer.
PROFILE = "PROFILE"
PREFERENCE = "PREFERENCE"
PROJECT = "PROJECT"
SKILL = "SKILL"
GOAL = "GOAL"
WORKFLOW = "WORKFLOW"
CONSTRAINT = "CONSTRAINT"


_PATTERNS = [
    (r"my name is (.+)", "User's name is {}", PROFILE, "name", 5),
    (r"call me (.+)", "User's name is {}", PROFILE, "name", 5),

    (r"i am from (.+)", "User is from {}", PROFILE, "location", 4),
    (r"i live in (.+)", "User lives in {}", PROFILE, "location", 4),

    (r"i am a (.+)", "User is a {}", PROFILE, "role", 4),
    (r"i study at (.+)", "User studies at {}", PROFILE, "college", 4),
    (r"i work at (.+)", "User works at {}", PROFILE, "workplace", 4),
    (r"i work as a (.+)", "User works as a {}", PROFILE, "job", 4),
    (r"my job is (.+)", "User's job is {}", PROFILE, "job", 4),

    (
        r"my favorite language is (.+)",
        "User's favorite language is {}",
        PREFERENCE,
        "favorite_language",
        4,
    ),
    (
        r"my favorite framework is (.+)",
        "User's favorite framework is {}",
        PREFERENCE,
        "favorite_framework",
        4,
    ),
    (r"i prefer (.+)", "User prefers {}", PREFERENCE, "preference", 4),
    (r"i like (.+)", "User likes {}", PREFERENCE, "likes", 3),

    (r"my project is (.+)", "User's project is {}", PROJECT, "project", 5),
    (r"my goal is (.+)", "User's goal is {}", GOAL, "goal", 5),

    (r"remember that (.+)", "User note: {}", WORKFLOW, "note", 5),
    (r"keep in mind that (.+)", "User note: {}", WORKFLOW, "note", 5),
    (r"please remember (.+)", "User note: {}", WORKFLOW, "note", 5),
]


def _clean_value(value: str) -> str:
    value = value.strip().strip(".,!?;:")

    if "," in value:
        value = value.split(",")[0].strip()

    return value


def extract_memory_candidates(message: str) -> list[MemoryCandidate]:
    """
    Extract structured long-term memory candidates.

    This is the new production-oriented API.
    """
    candidates: list[MemoryCandidate] = []

    text = message.lower().strip()

    for pattern, template, category, key, importance in _PATTERNS:
        match = re.search(pattern, text)

        if not match:
            continue

        value = _clean_value(match.group(1))

        if not value or len(value) <= 1:
            continue

        fact = template.format(value.capitalize())

        candidate = MemoryCandidate(
            fact=fact,
            category=category,
            key=key,
            importance=importance,
        )

        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def extract_memories(message: str):
    """
    Backward-compatible memory extraction API.

    Existing code/tests continue receiving a list of strings.
    """
    return [
        candidate.fact
        for candidate in extract_memory_candidates(message)
    ]