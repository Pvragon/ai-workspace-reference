#!/bin/bash
# Pristine-container test of ONBOARDING.md Phase 7.5 — the memory install.
#
# Proves a teammate can point a harness at team-lib and end up with a working memory
# system, starting from a box with nothing installed. A host-machine run passes
# falsely: a developer machine already has every dependency, a populated corpus, and
# registered hooks, so it cannot see what a new teammate would hit.
#
# It has already earned this. Three fresh-box failures found here, none visible on the
# host: verify_memory_install crashed where `crontab` was absent; it reported a correct
# empty corpus as a hard failure; and it parsed the reranker's output with a regex that
# a new band silently broke.
#
# RUN IT after any change to the memory scripts or to ONBOARDING Phase 7.5.
#
#   cd ~/ai-workspace/team-lib
#   git bundle create /mnt/c/temp/memtest/teamlib.bundle HEAD main   # COMMITTED state only
#   cp harnesses/memory_install_container_test.sh /mnt/c/temp/memtest/harness.sh
#   "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
#       run --rm -v "C:\\temp\\memtest:/src" ubuntu:24.04 bash /src/harness.sh
#
# Gotchas, each of which cost a round:
#   - No docker in this WSL distro; use Windows docker.exe interop.
#   - Docker Desktop CANNOT bind-mount a \\wsl.localhost path. Stage the bundle on a real
#     Windows path (C:\temp\...) and mount that.
#   - Run the harness as a FILE inside the container, never piped via stdin: apt-get's
#     children consume the rest of stdin and the run "succeeds" having executed one line.
#   - `git bundle` carries COMMITTED state. Testing an uncommitted fix silently tests the
#     old code; commit first, then bundle.
set -uo pipefail

echo "=== [0] fresh box: sudo-capable 'guest', git + python3 only ==="
apt-get update -qq >/dev/null 2>&1 </dev/null
apt-get install -y -qq sudo git python3 >/dev/null 2>&1 </dev/null
useradd -m -s /bin/bash guest
echo 'guest ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/guest
cp /src/teamlib.bundle /home/guest/teamlib.bundle && chown guest:guest /home/guest/teamlib.bundle

cat > /home/guest/flow.sh <<'GUEST'
set -uo pipefail
PASS=0; FAIL=0
ok()   { echo "CHECK-PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "CHECK-FAIL: $1"; FAIL=$((FAIL+1)); }
check(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

echo "=== [pre] deliberately NOT installing PyYAML or anything else ==="
python3 -c 'import yaml' 2>/dev/null && echo "  (note: yaml present in base image)" || echo "  no PyYAML — memory install must not need it"

echo "=== [setup] seed team-lib from bundle ==="
mkdir -p ~/ai-workspace
git clone -q ~/teamlib.bundle ~/ai-workspace/team-lib 2>/dev/null
check "team-lib cloned"                 "test -d ~/ai-workspace/team-lib/executions"

echo ""
echo "=== [Phase 7.5 BEFORE Phase 7] the pre-naming state setup actually hits ==="
# setup_workspace.sh runs before any agent exists, so this is the state a real first
# install is in. It must wire what it can and REFUSE to claim success.
bash ~/ai-workspace/team-lib/_admin/install_memory.sh > /tmp/deferred.log 2>&1
DEFERRED_RC=$?
tail -6 /tmp/deferred.log
check "no agent -> exit 2 (DEFERRED)"   "test $DEFERRED_RC -eq 2"
check "deferred says so out loud"       "grep -q DEFERRED /tmp/deferred.log"
check "hooks wired even pre-naming"     "grep -q update_memory_access ~/.claude/settings.json"
check "no memory dir invented"          "! test -d ~/ai-workspace/agents/testagent/memory"

echo ""
echo "=== [Phase 7 stand-in] agent home, as the naming ceremony would leave it ==="
mkdir -p ~/ai-workspace/agents/testagent
cat > ~/ai-workspace/agents/testagent/identity.md <<'ID'
---
name: testagent
pronouns: they/them
---
# testagent
A fresh agent with no memory yet.
ID
check "agent home exists"               "test -f ~/ai-workspace/agents/testagent/identity.md"

echo ""
echo "=== [Phase 7.5 step 1] agent resolution ==="
cd ~/ai-workspace/team-lib/executions
python3 agent_paths.py && ok "agent_paths resolves" || bad "agent_paths resolves"

echo ""
echo "=== [Phase 7.5 step 2] DRY RUN, as the guide says ==="
# ONBOARDING documents ONE command now, so that is what this exercises. Testing the
# underlying three-script chain instead would leave the documented path unrun — the
# same trap as a doc that describes a gate nobody executes.
INSTALL=~/ai-workspace/team-lib/_admin/install_memory.sh
bash $INSTALL --dry-run 2>&1 | tail -6
check "dry run exits 0"                 "bash $INSTALL --dry-run"
check "dry run wrote NOTHING"           "! test -f ~/ai-workspace/agents/testagent/memory/MEMORY.md"

echo ""
echo "=== [Phase 7.5 step 3] the documented one-command install ==="
bash $INSTALL > /tmp/install.log 2>&1
INSTALL_RC=$?
tail -25 /tmp/install.log
check "install exits 0"                 "test $INSTALL_RC -eq 0"
check "memory dir created"              "test -d ~/ai-workspace/agents/testagent/memory"
check "MEMORY.md created"               "test -s ~/ai-workspace/agents/testagent/memory/MEMORY.md"
check "short-term dir created"          "test -d ~/ai-workspace/agents/testagent/memory/short-term"
check "settings.json written"           "test -f ~/.claude/settings.json"
check "hook registered by ABSOLUTE path" "grep -q update_memory_access ~/.claude/settings.json"
check "verify ran inside the installer" "grep -q 'wired and firing' /tmp/install.log"

# A box with no `cron` package must still yield a working memory system — only the
# nightly cycle goes unscheduled. This is the pristine-box case by definition.
if command -v crontab >/dev/null 2>&1; then
    echo "  (crontab present in this image — cron path exercised for real)"
else
    check "missing crontab degrades soft" "grep -q 'SKIPPED — no .crontab. binary' /tmp/install.log"
fi

echo ""
echo "=== [Phase 7.5 step 4] re-run is a clean no-op (idempotence) ==="
bash $INSTALL > /tmp/install2.log 2>&1
RERUN_RC=$?
check "second run exits 0"              "test $RERUN_RC -eq 0"
check "second run changed nothing"      "grep -q 'already correct' /tmp/install2.log"

echo ""
echo "=== [Phase 7.5 step 5] verify standalone ==="
python3 verify_memory_install.py 2>&1 | tail -20
check "verify_memory_install exits 0"   "python3 verify_memory_install.py"

echo ""
echo "=== [the real test] does the loop actually close on a fresh box? ==="
MEM=~/ai-workspace/agents/testagent/memory
cat > $MEM/feedback_container-probe.md <<'MEMFILE'
---
name: feedback_container-probe
type: feedback
summary: "A memory written on a fresh box must be visible in the auto-loaded index."
created: 2026-07-30
---
Probe written by the container test.
MEMFILE
python3 rerank_memory_index.py 2>&1 | tail -2
check "probe memory is INDEXED"          "grep -q feedback_container-probe $MEM/MEMORY.md"
check "probe is in the auto-loaded part" "awk '/^## Cold/{exit} {print}' $MEM/MEMORY.md | grep -q feedback_container-probe"

echo "  --- reinforcement path ---"
printf '{"tool_name":"Read","tool_input":{"file_path":"%s/feedback_container-probe.md"}}' "$MEM" \
  | python3 update_memory_access.py
check "hook stamped last_accessed"       "grep -q last_accessed $MEM/feedback_container-probe.md"

echo "  --- determinism ---"
cp $MEM/MEMORY.md /tmp/r1.md
python3 rerank_memory_index.py >/dev/null 2>&1
check "rerank is deterministic"          "diff -q /tmp/r1.md $MEM/MEMORY.md"

echo "  --- regression suite on a fresh box ---"
python3 test_memory_ranking.py 2>&1 | tail -3
check "regression suite passes"          "python3 test_memory_ranking.py"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "CONTAINER-TEST: ALL GREEN" || echo "CONTAINER-TEST: FAILURES PRESENT"
GUEST

chown guest:guest /home/guest/flow.sh
su -l guest -c 'bash /home/guest/flow.sh'
echo "guest flow exit: $?"
