# Why `git checkout` is not enough to undo an agent

A coding agent deletes a file, then the tests fail. You reach for git. Sometimes it saves you.
The times it does not are the ones that hurt, and they are not rare: agents create, delete, move and
rewrite files that `git` has never seen — scratch notes, local configs, generated assets, a whole
directory someone forgot to add.

`git` can only restore what reached the object store. An untracked file that an agent deleted was
never there. `git checkout -- .` reports success and the file stays gone.

## Reproduce it

```bash
./examples/git-is-not-enough.sh
```

The script seeds a throwaway repo with one tracked file (`a.py`), one untracked file (`notes.txt`)
and one untracked directory (`sub/b.py`). An "agent" then edits, deletes and creates files, and the
gate fails. Recovery is attempted two ways. Output of a real run:

```text
=== 1. the agent runs, the gate fails, git is asked to recover ===
  a.py        : VALUE = 1
  notes.txt   : MISSING
  sub/b.py    : MISSING
  junk.log    : gone
  -> git lost the untracked file: it was never in the object store.

=== 2. same mess, but the command runs inside autocetacean guard ===
  a.py        : VALUE = 1
  notes.txt   : my uncommitted notes
  sub/b.py    : nested
  junk.log    : gone
  -> the guard restored the workspace before the agent's edits were ever accepted.
```

Same agent, same mess, same gate. The only difference is whether the command ran inside a snapshot.

## Use it

```bash
autocetacean guard --workspace . --cmd "claude -p 'fix the failing test'" --gate "pytest -q"
```

The command runs. If the gate passes, the edits stay. If it fails, the workspace is restored — every
modified file, every deleted file, every created file, every removed directory, whether or not git
tracked it.

## What this is and is not

It **is** transactional acceptance: nothing an agent does survives unless a deterministic command says
it is acceptable. The gate is any command that exits non-zero when the result is bad — a test suite, a
type check, a build, a schema check.

It **is not** a backup. The snapshot covers the workspace directory for the duration of one command. It
does not protect other disks, other machines, or anything an agent does outside that directory, and it
does not replace a remote. If an agent runs `rm -rf /`, a workspace guard is not what saves you.

Rule of thumb: use both. Backups for disasters, the guard for the ordinary case where an agent's
20-file refactor is 90% right and you cannot tell which 10% is wrong.

## Verified in a clean environment

Both the script and the output above were run inside a fresh `python3 -m venv` after:

```bash
pip install "autocetacean @ git+https://github.com/xunWhale/autocetacean"
```

installed `autocetacean 0.4.0`. No dependency was preinstalled; the package declares zero runtime
dependencies, and the script needs only `git` and `python3`.
