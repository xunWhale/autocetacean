#!/usr/bin/env bash
# Reproduces the case `git checkout` cannot undo and `autocetacean guard` can.
#
# Scenario: an agent edits a tracked file, deletes an untracked file, and wipes an
# untracked directory. The gate fails. Then we try to recover two ways.
#
#   ./examples/git-is-not-enough.sh            # run both recoveries side by side
#
# Requires: git, python3, autocetacean on PATH (or PYTHONPATH pointing at src/).
set -uo pipefail

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

seed() {  # $1 = directory
  mkdir -p "$1/sub"
  printf 'VALUE = 1\n' > "$1/a.py"
  printf 'my uncommitted notes\n' > "$1/notes.txt"
  printf 'nested\n' > "$1/sub/b.py"
  git -C "$1" init -q
  git -C "$1" add a.py
  git -C "$1" -c user.email=a@b -c user.name=probe commit -qm seed
}

agent_mess() {  # $1 = directory; the "agent" runs wild
  printf 'VALUE = 999\n' > "$1/a.py"   # edits a tracked file
  rm -f "$1/notes.txt"                 # deletes an untracked file
  rm -rf "$1/sub"                      # deletes an untracked directory
  printf 'junk\n' > "$1/junk.log"      # leaves a new file behind
}

report() {  # $1 = label, $2 = directory, $3 = notes content or MISSING, $4 = b.py content or MISSING
  printf '  a.py        : %s\n' "$(head -1 "$2/a.py")"
  printf '  notes.txt   : %s\n' "$3"
  printf '  sub/b.py    : %s\n' "$4"
  printf '  junk.log    : %s\n' "$([ -f "$2/junk.log" ] && echo "still there" || echo gone)"
}

echo "=== 1. the agent runs, the gate fails, git is asked to recover ==="
git_dir="$ROOT/git"; seed "$git_dir"; agent_mess "$git_dir"
git -C "$git_dir" checkout -- . 2>/dev/null
git -C "$git_dir" clean -fdq 2>/dev/null
notes=$(cat "$git_dir/notes.txt" 2>/dev/null || echo MISSING)
bypy=$(cat "$git_dir/sub/b.py" 2>/dev/null || echo MISSING)
report "git" "$git_dir" "$notes" "$bypy"
[ "$notes" = MISSING ] && echo "  -> git lost the untracked file: it was never in the object store."

echo
echo "=== 2. same mess, but the command runs inside autocetacean guard ==="
guard_dir="$ROOT/guard"; seed "$guard_dir"
( cd "$guard_dir" && autocetacean guard --workspace . --cmd "$(declare -f agent_mess); agent_mess ." \
    --gate "python3 -c 'import a; assert a.VALUE==1'" >/dev/null 2>&1 )
notes=$(cat "$guard_dir/notes.txt" 2>/dev/null || echo MISSING)
bypy=$(cat "$guard_dir/sub/b.py" 2>/dev/null || echo MISSING)
report "guard" "$guard_dir" "$notes" "$bypy"
[ "$notes" != MISSING ] && echo "  -> the guard restored the workspace before the agent's edits were ever accepted."
