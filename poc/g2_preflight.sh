#!/usr/bin/env bash
# Non-inference G2 preflight inside the disposable container.
# Mirrors the real global OpenCode config (the one carrying the 9Router provider),
# adapting only the baseURL for Docker networking. No model is invoked.
set +e

echo "=== versions ==="
python --version
python3 --version
git --version
opencode --version

echo "=== config setup ==="
mkdir -p /tmp/cfg
sed 's#http://127.0.0.1:20128/v1#http://host.docker.internal:20128/v1#' \
    /run/opencode-global.json > /tmp/cfg/opencode.json
cp -r /work/.opencode /tmp/cfg/.opencode
export OPENCODE_CONFIG=/tmp/cfg/opencode.json
export OPENCODE_CONFIG_DIR=
export OPENCODE_DISABLE_PROJECT_CONFIG=0
export OPENCODE_DISABLE_AUTOUPDATE=1
echo "OPENCODE_CONFIG=$OPENCODE_CONFIG"

echo "=== 9router routes ==="
opencode models | grep '^9router/'

echo "=== custom profile doctor ==="
python3 "$RUNNER" doctor --cli opencode-9router --config "$CONFIG"

echo "=== workspace baseline ==="
git -C "$G2_BASE/workspace" status --porcelain=v1 --untracked-files=all
git -C "$G2_BASE/workspace" log --oneline -1
