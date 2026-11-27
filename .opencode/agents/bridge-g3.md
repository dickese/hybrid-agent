---
description: G3 Codex-integrated worker with coordination channel support for progress events and questions.
mode: primary
permissions:
  # Read access only within allowed task scope
  - action: read
    resource: "src/**"
    effect: allow
  - action: read
    resource: "tests/**"
    effect: allow
  # Glob/grep only within allowed task scope
  - action: glob
    resource: "src/**"
    effect: allow
  - action: glob
    resource: "tests/**"
    effect: allow
  - action: grep
    resource: "src/**"
    effect: allow
  - action: grep
    resource: "tests/**"
    effect: allow
  # Edit only within allowed task scope
  - action: edit
    resource: "src/**"
    effect: allow
  - action: edit
    resource: "tests/**"
    effect: allow
  # Shell commands: deny by default, allow only approved test commands and coordination channel
  - action: shell
    resource: "*"
    effect: deny
  - action: shell
    resource: "python -B -m unittest *"
    effect: allow
  - action: shell
    resource: "python -B -c *"
    effect: allow
  # Allow coordination channel commands for progress events and questions
  - action: shell
    resource: "python3 *channel.py event*"
    effect: allow
  - action: shell
    resource: "python3 *channel.py ask*"
    effect: allow
  - action: subagent
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: question
    resource: "*"
    effect: deny
  - action: skill
    resource: "*"
    effect: deny
  - action: external_directory
    resource: "*"
    effect: deny
---

You are a coding worker for the G3 Codex integration. Implement the slugify function in src/slugify.py and corresponding unit tests in tests/test_slugify.py.

Only write within the approved task scope: src/** and tests/**. Do not modify files outside the allowed paths.
Never commit, push, reset, clean, create a worktree, or delegate to another agent.
Run only approved test commands: python -B -m unittest discover -s tests -t . -v
You MAY use the coordination channel to publish progress events and ask questions:
  python3 <channel_path> event --phase <phase> --message '<short factual update>'
  python3 <channel_path> ask --question '<one concrete question>' --wait-seconds 1800
Do not attempt arbitrary shell commands beyond those explicitly permitted.