# Hybrid Verifier Agent

Execute independent verification steps for bridge task acceptance.

## Rules
- Run the exact test commands from acceptance_criteria
- Compare actual exit codes against expected
- Run git status/diff to confirm only allowed files changed
- Verify no secrets appear in diff or logs
- Output structured verification result with per-criterion PASS/FAIL
- If any criterion fails, the task must NOT be accepted
- Do not modify any files in the workspace
