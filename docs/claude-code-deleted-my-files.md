# Claude Code deleted my files — what actually gets them back

This page is for the bad moment, in order: stop, work out which class of deletion you are in, then
use the recovery that can actually reach it. The prevention section at the end is short, because by
then you will know exactly which hole you fell through.

## 0. Stop the session first

Do not send another prompt. Do not let the agent "fix it". Every new turn is another checkpoint and
another set of edits on top of the state you are trying to recover. Close the session, note the
session id if you have it, and keep the terminal scrollback — it names the commands that ran.

## 1. Which class are you in?

Claude Code's own `/rewind` (alias `/undo`) restores files that **its file-editing tools** changed,
and its documented limits decide whether it can help you. The official page is
[Checkpointing](https://code.claude.com/docs/en/checkpointing); these are the limits that bite:

| What happened | Does `/rewind` restore it? |
| --- | --- |
| The Edit/Write tool changed the file | Yes, if the snapshot still exists |
| Only a **Bash command** changed the file (`rm`, `mv`, `cat >`, a generator script) | **No** — "A file that only Bash commands changed isn't tracked and stays as it is" |
| A **subagent** changed files | **No**, unless it was a foreground forked skill |
| The file is a **symlink or hard link** | **No** — the restore skips it and warns "Restored the code, but skipped N files" |
| The checkpoint is older than the last 100, or 30 days old | **No** — snapshots are pruned |

So before you open the rewind menu, answer one question: did the loss come from the agent's editor,
or from a shell command it ran? If a shell command did it, `/rewind` will show "no file changes" and
you need section 2.

## 2. Recover by source, not by hope

**If the agent used a shell command**, the file was unlinked or overwritten at the filesystem level.
Version control is the first thing that can reach it:

```bash
git status                       # what is gone or dirty
git checkout -- path/to/file     # only works if the file was committed at least once
git stash list                   # if someone stashed before the mess
git fsck --lost-found            # blobs from a commit that was reset away
```

`git checkout` restores tracked content only. A file that was **never committed** is not in the
object store, and no git command can bring it back. That includes the common case: a notes file, a
scratch directory, a generated asset, a whole new module the agent created last week and you had not
committed yet.

**If the file was never committed**, the remaining sources are, in order of how often they work:

1. **The OS trash.** `rm` from a shell does not use the trash, but file managers, IDEs, and some
   tools do. Check `~/.local/share/Trash/files` (Linux), `~/.Trash` (macOS).
2. **A filesystem snapshot.** btrfs: `snapper list` / `btrfs subvolume list`. ZFS: `zfs list -t
   snapshot`. macOS Time Machine: `tmutil listlocalsnapshots /`. Windows: Volume Shadow Copy.
   These are the only mechanism that can return a file that was never in git and never in the trash.
3. **An editor's local history.** VS Code keeps `~/.config/Code/User/History`; JetBrains keeps
   Local History per project. If you ever opened the file, a copy may be there.
4. **A backup.** If none of the above applies, this is the only path left, and the honest answer is
   that unrecovered means unrecovered.

## 3. Prevention that covers the case git cannot

The gap is always the same: **content that never reached git, changed by a shell command, inside a
directory an agent has write access to.** Three things close it, in increasing order of effort:

**Deny rules for the destructive commands.** In `.claude/settings.json`, refuse the commands that do
bulk damage:

```json
{
  "permissions": {
    "deny": ["Bash(rm -rf:*)", "Bash(git reset --hard:*)", "Bash(git clean:*)"]
  }
}
```

This is cheap and it stops the common accident. It does not stop a script the agent writes and then
runs, which is where the bigger losses come from.

**A container or a throwaway checkout.** If the work does not need to touch your real tree, run the
agent against a copy. Strongest isolation, but it does not help when the agent is supposed to edit
your actual project.

**A transaction around the command.** Snapshot the workspace before the command, and only keep the
result if a check passes. This project ships that as one command:

```bash
autocetacean guard --workspace . --cmd "claude -p 'fix the failing test'" --gate "pytest -q"
```

If the gate fails, every file the agent touched is put back — including untracked files and deleted
directories, which is exactly the class `/rewind` and `git checkout` both miss. What it is **not** is
a recovery tool: it has to be running before the damage, so it belongs in this section, not in
section 2. Its limits are in [Why not just git?](why-not-just-git.md).

## The one-line version

`/rewind` covers the agent's editor. `git` covers what you committed. Filesystem snapshots cover the
rest. If nothing was covering the file, it is gone — so put something under the agent before the next
run, not after.
