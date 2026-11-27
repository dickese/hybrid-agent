# Objective

Implement `slugify(text: str) -> str` in `src/slugify.py` and deterministic unit tests in `tests/test_slugify.py` for a disposable PoC workspace.

# Why

This is a small, fully specified coding task used to verify that the orchestrated OpenCode worker can make a scoped, independently verifiable change through the approved route.

# Scope

Create or modify only these files in the workspace root:

- `src/slugify.py`
- `tests/__init__.py`
- `tests/test_slugify.py`

Do not touch any other file. Do not read files outside the workspace.

# Files to inspect

- `README.md`
- `.opencode/agents/bridge-build.md` (the execution profile)

# Implementation guidance

- Use only the Python standard library (`re`, `unicodedata`).
- Normalize text with Unicode NFKD and drop combining marks so accented Latin letters become ASCII (`Café` → `Cafe`).
- Lowercase the result.
- Replace every run of characters that are not ASCII letters or digits with a single hyphen.
- Strip leading and trailing hyphens.
- Return an empty string when no alphanumeric character remains.
- Add an empty `tests/__init__.py` so discovery works from the workspace root.

# Constraints

- Do not modify files outside the Scope.
- Do not commit, push, reset, clean, create branches, or create worktrees.
- Do not use the network.
- Run only this test command **after implementation**: `python -B -m unittest discover -s tests -t . -v`
- If the coordination-channel command is denied by the execution profile, continue without progress events.
- **IMPORTANT: Your current working directory (run `pwd` to verify) IS the workspace root. It is NOT `/work`. `/work` is a read-only mount of the upstream repository. Do not attempt to write to `/work`. All file operations must be relative to your current working directory.**
- **Do not change your working directory. Do not use `session_move`, `cd`, or any command that changes the working directory. The `.opencode/agents/bridge-build.md` profile must remain accessible.**
- **Use ONLY relative paths (e.g., `src/slugify.py`, `tests/test_slugify.py`). Do NOT use absolute paths like `/g2/state/jobs/...` or any path starting with `/`. The coordination preamble may reference absolute paths for internal channels — ignore them and work only in your current directory.**
- **The workspace root is at `/tmp/g2-workspace` (container tmpfs). This is where you must create `src/slugify.py` and `tests/test_slugify.py`.**

# Acceptance criteria

- `src/slugify.py` exposes `slugify`.
- `tests/test_slugify.py` covers all required cases and passes.
- No out-of-scope files change.

# Validation

Run exactly from the workspace root:

```bash
python -B -m unittest discover -s tests -t . -v
```

Report the number of tests run and whether they passed. Do not include secrets in the report.

# Final report

Report the files created, the exact test command, and the pass/fail summary.