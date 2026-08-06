---
name: worktree-remove
description: Remove an opendlp git worktree (a sibling folder named opendlp-worktree-<branch>) safely. Invoke when the user asks to remove/delete/clean up a worktree.
argument-hint: <branch-name>
---

# Remove an opendlp worktree

Remove the worktree for the branch given in the arguments. Worktrees live as siblings of the main repo, named `opendlp-worktree-<branch-name>`.

If no branch name was passed, run `git worktree list` and ask the user which one to remove.

## Steps

Run all git commands from the main repo (`/Users/macintosh/Sites/opendlp`).

1. **Locate it.** Run `git worktree list` and confirm a worktree for this branch exists. If not, say so and stop.

2. **Safety check.** Inspect the worktree before deleting anything:
   ```bash
   git -C ../opendlp-worktree-<branch> status --porcelain
   git -C ../opendlp-worktree-<branch> log --oneline @{upstream}..HEAD 2>/dev/null
   ```
   If there are uncommitted changes or unpushed commits, STOP and tell the user exactly what would be lost. Only proceed with `--force` after they explicitly confirm.

3. **Remove.**
   ```bash
   git worktree remove ../opendlp-worktree-<branch>
   git worktree prune
   ```

4. **Report.** Confirm the folder is gone. Note that the local branch `<branch>` still exists in the main repo; do NOT delete it unless the user asks — if they do, use `git branch -d <branch>` (only escalate to `-D` after warning about unmerged commits and getting confirmation).
