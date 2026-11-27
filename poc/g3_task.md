# G3 Task Contract: Slugify Function Implementation

## Objective
Implement a `slugify` function in `src/slugify.py` that converts arbitrary strings into URL-safe slugs. Create corresponding unit tests in `tests/test_slugify.py`.

## Acceptance Criteria
- Function `slugify(text: str) -> str` exists in `src/slugify.py`
- Handles Unicode normalization (NFKD) and ASCII transliteration
- Converts to lowercase
- Replaces whitespace and special characters with single hyphens
- Strips leading/trailing hyphens
- Returns empty string for empty or only-special-char input
- Unit tests cover all 8 reference cases (see below)
- All tests pass with `python -B -m unittest discover -s tests -t . -v`

## Reference Test Cases
| Input | Expected Output |
|-------|-----------------|
| "Hello, World!" | "hello-world" |
| "  Multiple   spaces  " | "multiple-spaces" |
| "Café Déjà Vu" | "cafe-deja-vu" |
| "Python 3.11" | "python-3-11" |
| "A_B.C" | "a-b-c" |
| "Über Cool" | "uber-cool" |
| "---" | "" |
| "" | "" |

## Allowed Paths
- src/**
- tests/**

## Denied Paths
- .opencode/**
- AGENTS.md
- handoff/**
- config/**
- docs/**
- scripts/**
- bridge/**
- poc/**
- examples/**

## Constraints
- Do not modify files outside allowed paths
- Do not commit, push, or create worktrees
- Do not delegate to another agent
- Use only approved test commands
- Coordination channel available for progress events and questions