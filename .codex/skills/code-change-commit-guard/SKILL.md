---
name: code-change-commit-guard
description: "Enforce the finish-workflow for code changes: add concise comments to new methods when needed, create a focused git commit after code edits, explain the changes in natural language, and roll back the latest version when the user asks."
---

# Code Change Commit Guard

Follow this workflow whenever you finish a code-change task.

## Workflow

1. Identify the exact files that belong to the current task.
2. While editing code, add concise comments to new methods when the intent is not obvious.
3. Run the minimum useful verification and inspect `git diff`.
4. Stage only the files for the current task.
5. Create one focused git commit.
6. In the reply, explain:
   - what changed;
   - why it changed;
   - what was verified;
   - the commit hash.

## Comment Rules

- Add comments only where they save future readers time.
- Explain purpose, key constraints, input/output, or the reason behind a non-obvious choice.
- Do not add filler comments to trivial methods.

## Commit Rules

- Use a short and direct commit message.
- Check `git status --short` before and after staging.
- Do not include unrelated user changes in the commit.
- If the task does not change code, do not create an empty commit just to satisfy process.

## Rollback Rules

- When the user says "rollback", "revert", or "undo the latest version", target the latest commit you created for the current task.
- If the working tree is clean and the user clearly wants to go back to the previous version, return to the state before the latest commit.
- If the working tree is not clean, or history should be preserved, prefer a history-preserving rollback and explain that choice.
- After rollback, report what was undone and the current commit state.

## Suggested Commands

Use this order in PowerShell:

```powershell
git status --short
git diff -- <path>
git add -- <path>
git diff --cached -- <path>
git commit -m "<message>"
```

Before rolling back the latest version:

```powershell
git status --short
git log --oneline -1
```

## Reply Checklist

After a code change, cover these points:

1. change summary
2. added comments
3. verification
4. commit message and commit hash

After a rollback, cover these points:

1. rollback target
2. git method used
3. current commit state
