#!/bin/bash
# ---
# template: harness
# version: 1.0.3
# summary: "Pristine-container proof that the PUBLISHED workspace (ai-workspace-reference)
#   can be cloned onto a blank box, run through the ONBOARDING it ships, and end with a
#   working agent. Installs from the published bytes only — no host state, no private repo."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Pristine-container test of the PUBLISHED workspace — the whole ONBOARDING path.
#
# Sibling of memory_install_container_test.sh, one layer up: that one proves Phase 7.5
# installs a memory system on a fresh box; this one proves the artifact we publish to the
# world (ai-workspace-reference) can be cloned onto a blank machine, run through the
# ONBOARDING it itself ships, and end with a working agent.
#
# Why the PUBLISHED bytes and not team-lib directly. Publication is a transform — a file
# map, a scrub list, submodules materialized into plain files. Every one of those can
# silently drop something the install depends on, and nothing on a developer machine can
# see it: the host already has team-lib, the submodules, the toolchain and a populated
# agent. The only way to know is to install from the published side, on a box with nothing.
#
# What is substituted, and why each substitution is honest:
#   1. ONBOARDING Phase 3 clones the PRIVATE installer repo (Pvragon/pvragon-ai-library),
#      whose ROOT is team-lib. The public repo carries the same content one level down at
#      team-lib/. So the container derives an installer origin with
#      `git subtree split --prefix=team-lib` over the published bundle and points
#      TEAM_REPO_URL at it. Only published bytes are used, and no network or private
#      access is involved.
#   2. setup_workspace.sh asks four questions. They are answered from a file, exactly as
#      ONBOARDING Phase 3 instructs a human to answer them.
# Everything else runs as published. Any other failure is a finding, not a harness bug.
#
#   cd ~/ai-workspace/projects/ai-workspace-reference
#   mkdir -p /mnt/c/temp/wstest
#   git bundle create /mnt/c/temp/wstest/public.bundle HEAD main   # COMMITTED state only
#   cp ~/ai-workspace/team-lib/harnesses/public_workspace_container_test.sh \
#      /mnt/c/temp/wstest/harness.sh
#   python3 -c "import yaml;print('\\n'.join(t for ts in \
#     yaml.safe_load(open('registry/mirror.yaml'))['publication']['scrub'].values() \
#     for t in ts))" > /mnt/c/temp/wstest/scrub-tokens.txt   # never hard-code these
#   "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
#       run --rm -v "C:\\temp\\wstest:/src" ubuntu:24.04 bash /src/harness.sh
#
# Gotchas inherited from the memory harness, each of which cost a round there:
#   - No docker in this WSL distro; use Windows docker.exe interop.
#   - Docker Desktop CANNOT bind-mount a \\wsl.localhost path. Stage on C:\temp\... .
#   - Run the harness as a FILE inside the container, never piped via stdin: apt-get's
#     children consume the rest of stdin and the run "succeeds" having executed one line.
#   - `git bundle` carries COMMITTED state. Commit first, then bundle.
# And one of its own:
#   - This run NEEDS network (apt, npm, git submodules) where the memory run needed none.
#     Budget 15-30 minutes.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "=== [0] fresh box: sudo + git only. Everything else must come from setup_system.sh ==="
apt-get update -qq >/dev/null 2>&1 </dev/null
apt-get install -y -qq sudo git ca-certificates >/dev/null 2>&1 </dev/null
useradd -m -s /bin/bash guest
echo 'guest ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/guest
# Two audiences, two install paths, one harness. Stage public.bundle to test what a stranger
# gets; stage teamlib.bundle to test what a Pvragon teammate gets (the private repo, whose root
# IS team-lib, with real submodule gitlinks). Testing only one leaves the other's claim unproven
# — and they differ in exactly the places that break: external packs, registries, remotes.
for b in public.bundle teamlib.bundle; do
    [[ -f "/src/$b" ]] && cp "/src/$b" "/home/guest/$b" && chown guest:guest "/home/guest/$b"
done

cat > /home/guest/answers.txt <<'ANSWERS'
Test Guest
guest@example.test
2
1
ANSWERS

cat > /home/guest/flow.sh <<'GUEST'
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
PASS=0; FAIL=0
FAILED_CHECKS=""
ok()   { echo "CHECK-PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "CHECK-FAIL: $1"; FAIL=$((FAIL+1)); FAILED_CHECKS="${FAILED_CHECKS}
  - $1"; }
check(){ if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

WS=~/ai-workspace
TL=$WS/team-lib

if [ -f ~/teamlib.bundle ]; then MODE=team; else MODE=public; fi
echo "=== [Phase 3.0] INSTALL PATH UNDER TEST: $MODE ==="

if [ "$MODE" = "team" ]; then
    # The teammate's path: the private repo, whose ROOT is team-lib, with real gitlinks.
    git clone -q --bare ~/teamlib.bundle ~/pvragon-ai-library.git 2>/dev/null
    git -C ~/pvragon-ai-library.git symbolic-ref HEAD refs/heads/main 2>/dev/null
    check "team repo cloned"                 "git -C ~/pvragon-ai-library.git rev-parse main"
    git clone -q ~/pvragon-ai-library.git ~/public-ref-src 2>/dev/null
    mkdir -p ~/public-ref && rm -rf ~/public-ref/team-lib && mv ~/public-ref-src ~/public-ref/team-lib
else
    git clone -q ~/public.bundle ~/public-ref 2>/dev/null
fi
check "repo cloned"                      "test -d ~/public-ref/team-lib/_admin"
check "repo ships ONBOARDING"            "test -s ~/public-ref/team-lib/ONBOARDING.md"
check "repo ships setup_system"          "test -s ~/public-ref/team-lib/_admin/setup_system.sh"
check "repo ships setup_workspace"       "test -s ~/public-ref/team-lib/_admin/setup_workspace.sh"
check "repo ships install_memory"        "test -s ~/public-ref/team-lib/_admin/install_memory.sh"

# The published repo must not carry the operator's real identity. This is the one check
# that is cheaper here than anywhere else: the whole corpus is on disk, unfiltered.
#
# The tokens are STAGED, never written here. Spelling them out would put the very strings
# publication blocks into a file publication publishes — which is exactly what happened,
# and the publisher's own scrub gate refused this harness until it was fixed. A missing
# token file is reported as NOT CHECKED and counted as a failure: a scrub check that
# silently did not run must never read as a scrub check that passed.
echo "=== [scrub] no operator PII in the published bytes ==="
if [ "$MODE" = "team" ]; then
    echo "  (team path: the private repo legitimately carries operator and client identifiers — scrub applies to publication only)"
elif [ -s /src/scrub-tokens.txt ]; then
    while read -r token; do
        [ -z "$token" ] && continue
        if grep -ril --exclude-dir=.git -- "$token" ~/public-ref >/dev/null 2>&1; then
            bad "published repo leaks a blocked identifier (${#token} chars)"
        else
            ok "published repo carries no blocked identifier (${#token} chars)"
        fi
    done < /src/scrub-tokens.txt
else
    bad "scrub check NOT CHECKED — /src/scrub-tokens.txt was not staged"
fi

echo ""
echo "=== [Phase 3.0b] derive the installer origin from published bytes only ==="
if [ "$MODE" = "team" ]; then
  echo "  (team path: the cloned repo IS the installer origin; no derivation needed)"
else
# ONBOARDING clones a repo whose ROOT is team-lib; the public repo nests it one level
# down. subtree-split reproduces the private repo's shape without inventing content.
cd ~/public-ref
# Identity via env, NOT `git config --global` — the global config must stay empty so that
# setup_workspace.sh's own git-identity prompt is still exercised below.
GIT_COMMITTER_NAME="harness" GIT_COMMITTER_EMAIL="harness@example.test" \
    git subtree split --prefix=team-lib -b teamlib-root >/dev/null 2>&1
git init -q --bare ~/pvragon-ai-library.git
git push -q ~/pvragon-ai-library.git teamlib-root:refs/heads/main 2>/dev/null
git -C ~/pvragon-ai-library.git symbolic-ref HEAD refs/heads/main
check "installer origin built from public bytes" "git -C ~/pvragon-ai-library.git rev-parse main"
fi
cd ~

echo ""
echo "=== [Phase 3.2] sudo setup_system.sh — the documented system install ==="
sudo -E bash ~/public-ref/team-lib/_admin/setup_system.sh > /tmp/system.log 2>&1
SYS_RC=$?
tail -12 /tmp/system.log
check "setup_system exits 0"             "test $SYS_RC -eq 0"
check "setup_system claims complete"     "grep -q 'System setup complete' /tmp/system.log"
for t in python3 pip3 node npm jq gh rg sqlite3; do
    check "toolchain present: $t"        "command -v $t"
done
# parse_toolchain.py imports yaml with the SYSTEM python3, not the venv.
check "system python3 has yaml"          "python3 -c 'import yaml'"
# claude and gws both declare engines node>=22; Ubuntu 24.04's apt ships 18.19.
check "node satisfies claude/gws (>=22)" "test \"\$(node -v | sed -E 's/^v([0-9]+).*/\1/')\" -ge 22"

echo ""
echo "=== [Phase 3.3] setup_workspace.sh — answers fed exactly as ONBOARDING says ==="
TEAM_REPO_URL="file:///home/guest/pvragon-ai-library.git" \
    bash ~/public-ref/team-lib/_admin/setup_workspace.sh < ~/answers.txt > /tmp/workspace.log 2>&1
WS_RC=$?
tail -30 /tmp/workspace.log
check "setup_workspace exits 0"          "test $WS_RC -eq 0"
check "setup_workspace says complete"    "grep -q '=== Setup complete! ===' /tmp/workspace.log"
check "it did NOT stall on a prompt"     "! grep -q 'Invalid option' /tmp/workspace.log"

echo ""
echo "--- Phase 3 checkpoint, as ONBOARDING states it ---"
for d in agents my-lib personal projects team-lib; do
    check "root exists: $d"              "test -d $WS/$d"
done
check "code-workspace generated"         "test -s $WS/pvragon-workspace.code-workspace"
check "manifest generated"               "test -s ~/.ai-workspace-manifest.yaml"
check "agents/ left empty (christening)" "test -z \"\$(ls -A $WS/agents)\""

echo ""
echo "--- team-lib arrived intact ---"
for d in _admin context directives executions harnesses personas registry skills; do
    check "team-lib/$d present"          "test -d $TL/$d"
done
check "governance directive present"     "test -s $TL/directives/team-library-governance.md"
check "skills registry present"          "test -s $TL/registry/skills.yaml"
# The humanizer gate is a hard rule in AGENTS.md; an empty pack silently disables it.
for pack in anthropics rezvani-claude-skills blader-humanizer; do
    check "external pack has content: $pack" "test -n \"\$(ls -A $TL/skills/_external/$pack 2>/dev/null)\""
done
check "humanizer SKILL.md resolves"      "test -s $TL/skills/_external/blader-humanizer/SKILL.md"

echo ""
echo "--- my-lib scaffolded and wired ---"
check "my-lib is a git repo"             "test -d $WS/my-lib/.git"
check "AGENTS.md installed"              "test -s $WS/my-lib/AGENTS.md"
check "CLAUDE.md installed"              "test -s $WS/my-lib/CLAUDE.md"
check "GEMINI.md installed"              "test -s $WS/my-lib/GEMINI.md"
# ONBOARDING Phase 6 asks the agent about artifact mirroring; the answer has to be IN
# the file it loads, or the checkpoint is unanswerable.
check "AGENTS.md answers the Phase 6 question" \
      "grep -q 'runtime/deliverables' $WS/my-lib/AGENTS.md"
check "python venv created"              "test -x $WS/my-lib/.venv/bin/python"
# Assert the packages base-requirements.txt actually lists. Naming them explicitly is the
# point: a check against some other import would pass on a venv that installed nothing.
check "base requirements installed"      "$WS/my-lib/.venv/bin/python -c 'import googleapiclient, google.auth, PIL, numpy'"
check ".env created from template"       "test -f $WS/personal/secrets/.env"

echo ""
echo "--- toolchain provisioning, as ONBOARDING Phase 6 promises it ---"
sed -n '/---> CLI Tools/,/Toolchain setup complete/p' /tmp/workspace.log | head -25
# Phase 6 states plainly: "Claude Code was installed during Phase 3 (it's part of the
# standard toolchain)." toolchain.yaml marks claude and gws required:true.
export PATH="$HOME/.npm-global/bin:$PATH"
check "claude on PATH after setup"       "command -v claude"
check "gws on PATH after setup"          "command -v gws"

echo ""
echo "--- memory correctly DEFERRED, not silently skipped ---"
check "setup reports the deferred step"  "grep -q 'Name your agent' /tmp/workspace.log"
check "no memory dir invented"           "test -z \"\$(find $WS/agents -maxdepth 2 -type d -name memory 2>/dev/null)\""

echo ""
echo "=== [Phase 4.3] validate.sh — ONBOARDING's own checkpoint ==="
bash $TL/_admin/validate.sh > /tmp/validate.log 2>&1
VAL_RC=$?
grep -E 'FAIL|WARN|passed|valid' /tmp/validate.log | head -30
check "validate.sh exits 0 (green)"      "test $VAL_RC -eq 0"
echo "  validate: $(grep -c 'FAIL' /tmp/validate.log) fail line(s), $(grep -c 'WARN' /tmp/validate.log) warn line(s)"

echo ""
echo "=== [Phase 7 stand-in] the christening, non-interactively ==="
# choose-name needs a live agent session, which a container has no way to run. --agent is
# the documented non-interactive equivalent and lands in the same place.
bash $TL/_admin/install_memory.sh --agent testagent > /tmp/memory.log 2>&1
MEM_RC=$?
tail -20 /tmp/memory.log
check "install_memory exits 0"           "test $MEM_RC -eq 0"
check "agent home created"               "test -d $WS/agents/testagent"
check "MEMORY.md created"                "test -s $WS/agents/testagent/memory/MEMORY.md"
check "MEMORY.md has a Hot band"         "grep -q '## Hot' $WS/agents/testagent/memory/MEMORY.md"
check "hooks registered"                 "grep -q update_memory_access ~/.claude/settings.json"
check "installer verified its own wiring" "grep -q 'wired and firing' /tmp/memory.log"

echo ""
echo "=== [Phase 4.3 again] validate.sh now that an agent exists ==="
bash $TL/_admin/validate.sh > /tmp/validate2.log 2>&1
VAL2_RC=$?
grep -E 'FAIL' /tmp/validate2.log | head -20
check "validate.sh exits 0 with an agent" "test $VAL2_RC -eq 0"

echo ""
echo "=== [Phase 8] can the agent actually USE the library it was given? ==="
# Phase 8's first task is 'read team-lib/registry/skills.yaml and tour three skills'.
# That resolves paths out of the registry, so every registered path must exist in the
# fresh install. A publication that drops files leaves the registry pointing at nothing.
python3 - <<'PYCHECK' > /tmp/integrity.log 2>&1
import os, re, sys, glob
try:
    import yaml
except ImportError:
    print("BROKEN: PyYAML missing for system python3"); sys.exit(3)

TL = os.path.expanduser("~/ai-workspace/team-lib")
WS = os.path.expanduser("~/ai-workspace")
# Most registries write team-lib-relative paths; workspace.yaml describes the workspace
# itself and writes `personal`, `my-lib`, `team-lib/_admin`. An agent resolving a registry
# entry tries both, so a checker that only tries one invents seven broken entries.
ROOTS = [TL, WS]
missing = []
checked = 0
for reg in sorted(glob.glob(os.path.join(TL, "registry", "*.yaml"))):
    try:
        data = yaml.safe_load(open(reg))
    except Exception as e:
        print(f"UNPARSEABLE {os.path.basename(reg)}: {e}")
        continue
    def walk(node):
        global checked
        if isinstance(node, dict):
            p = node.get("path")
            # Glob PATTERNS are not paths. mirror.yaml states its mapping as globs
            # (`_admin/**`), and treating those as files invented three broken entries
            # on the team path — the only path that sees mirror.yaml, since publication
            # excludes it. A checker that cannot tell a pattern from a path fails the
            # artifact for being written correctly.
            if (isinstance(p, str) and p and not p.startswith(("http", "~"))
                    and not any(ch in p for ch in "*?[")):
                checked += 1
                if not any(os.path.exists(os.path.join(root, p)) for root in ROOTS):
                    missing.append((os.path.basename(reg), p))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
print(f"REGISTRY: {checked} registered path(s) checked, {len(missing)} missing")
for reg, p in missing[:25]:
    print(f"  MISSING {reg}: {p}")

# The published entry-point docs are the only map a stranger has. A link that 404s in the
# repo is the same class of hole as a registry path that does not resolve.
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
badlinks = []
docs = 0
for md in sorted(glob.glob(os.path.join(TL, "*.md"))):
    docs += 1
    base = os.path.dirname(md)
    for target in LINK.findall(open(md, encoding="utf-8", errors="replace").read()):
        t = target.split("#")[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.join(base, t)):
            badlinks.append((os.path.basename(md), t))
print(f"DOCLINKS: {docs} root doc(s) scanned, {len(badlinks)} broken relative link(s)")
for md, t in badlinks[:25]:
    print(f"  BROKEN {md} -> {t}")
sys.exit(0 if not missing and not badlinks else 1)
PYCHECK
INTEG_RC=$?
cat /tmp/integrity.log
check "every registered path resolves"   "grep -q 'REGISTRY: .* 0 missing' /tmp/integrity.log"
check "no broken links in published docs" "grep -q 'DOCLINKS: .* 0 broken' /tmp/integrity.log"

# A skill is invoked by the harness as /name, which resolves through ~/.claude/skills.
# If setup never wires that, the agent has a library it cannot call. Presence alone is not
# enough — an empty directory would satisfy it while the library stayed unreachable.
check "skills reachable from the harness" "test -e ~/.claude/skills"
VISIBLE=$(find -L ~/.claude/skills -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)
SHIPPED=$(find $TL/skills -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)
echo "  skills visible to the harness: $VISIBLE (team-lib ships $SHIPPED at top level)"
check "harness sees the shared skills"   "test \"$VISIBLE\" -ge \"$SHIPPED\" -a \"$SHIPPED\" -gt 0"

# Finally, run a real library script end to end on the fresh box.
check "agent_paths resolves the new agent" "python3 $TL/executions/agent_paths.py"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
    echo "CONTAINER-TEST: ALL GREEN"
else
    echo "CONTAINER-TEST: FAILURES PRESENT"
    echo "Failed checks:$FAILED_CHECKS"
fi
GUEST

chown guest:guest /home/guest/flow.sh /home/guest/answers.txt
su -l guest -c 'bash /home/guest/flow.sh'
echo "guest flow exit: $?"
