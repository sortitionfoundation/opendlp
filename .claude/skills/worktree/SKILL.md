---
name: worktree
description: Create (or open) a git worktree for a branch as a sibling folder of the opendlp repo, named opendlp-worktree-<branch>. Handles both existing remote branches and brand-new branches. Invoke when the user asks to create/open/set up a worktree for a branch.
argument-hint: <branch-name>
---

# Create an opendlp worktree

Create a git worktree for the branch given in the arguments. The worktree folder is always a **sibling of the main opendlp checkout**, named `opendlp-worktree-<branch-name>` (e.g. `/Users/macintosh/Sites/opendlp-worktree-613-require-reg-fields`). Never use a `worktrees/` subdirectory or any other location/naming variant.

If no branch name was passed as an argument, ask the user which branch to use.

## Steps

Run all git commands from the main repo (`/Users/macintosh/Sites/opendlp`).

1. **Short-circuit if it already exists.** Run `git worktree list`. If a worktree for this branch already exists, just report its path and stop — don't recreate it.

2. **Fetch and check the remote.**
   ```bash
   git fetch origin
   git ls-remote --exit-code --heads origin <branch>
   ```

3. **If the remote branch exists** (exit code 0), create the worktree from it:
   ```bash
   git worktree add ../opendlp-worktree-<branch> <branch>
   ```
   Git will create a local branch tracking `origin/<branch>` automatically. If a local branch already exists, this checks it out in the worktree — that's fine, but if git complains the local branch is behind/diverged from the remote, report that to the user instead of forcing anything.

4. **If there is no remote branch**, create a new branch **from the current HEAD of the main opendlp checkout** and check it out directly in the new worktree (the main checkout stays on its current branch — never switch branches in the main repo):
   ```bash
   git worktree add -b <branch> ../opendlp-worktree-<branch>
   ```
   If the user asks for the branch to be based on main (or another ref) instead, pass that ref as the last argument, e.g. `git worktree add -b <branch> ../opendlp-worktree-<branch> origin/main`.

   **Upstream fix:** when the start point is a remote-tracking ref like `origin/main`, git auto-sets it as the new branch's upstream, which would make pull/push target the wrong remote branch. Clear it:
   ```bash
   git -C ../opendlp-worktree-<branch> branch --unset-upstream
   ```
   (Not needed when branching from HEAD — no upstream gets set — and the first `git push -u origin <branch>` will then wire up the correct one.)

5. **Verify and report.** Run `git worktree list` to confirm, then tell the user:
   - the absolute path of the new worktree,
   - which branch it's on and whether it tracks a remote branch or is brand new (and from which commit it was branched),
   - a reminder that untracked files like `.env`/local config are NOT carried over into a new worktree — offer to copy them from the main checkout if the project needs them to run.
