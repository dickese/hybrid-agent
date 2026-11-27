import sys
for line in sys.stdin:
    line = line.strip()
    if '=' in line:
        k, v = line.split('=', 1)
        if k in ['AGENT_ORCHESTRATOR_HOME', 'OPENCODE_CONFIG', 'OPENCODE_PROJECT_DIR', 'OPENCODE_CWD', 'G3_CLI', 'G3_MODEL', 'G3_CLI_AGENT', 'OPENCODE_DISABLE_AUTOUPDATE', 'OPENCODE_DISABLE_PROJECT_CONFIG', 'OPENCODE_CONFIG_DIR']:
            print(k + '=' + v)