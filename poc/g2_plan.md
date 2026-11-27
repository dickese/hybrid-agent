# Goal

Ship the bounded `slugify` utility with deterministic unit tests in the disposable PoC workspace.

# Decisions and assumptions

- Use the Python standard library only.
- Keep the change inside `src/` and `tests/`.

# Constraints and guardrails

- No commits, pushes, branches, or worktrees.
- No network access.
- No edits outside the task scope.

# Checklist

- [ ] Implement slugify and deterministic tests

# Validation strategy

Run `python -B -m unittest discover -s tests -t . -v` from the workspace root and require a clean pass.

# Completion criteria

Independent review accepts the diff only after the test command passes.
