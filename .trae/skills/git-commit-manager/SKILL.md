---
name: "git-commit-manager"
description: "Automatically commits code changes after AI modifications and provides git reset functionality. Invoke after every code change task or when user asks to commit/rollback changes."
---

# Git Commit Manager

This skill ensures all code modifications made by AI are properly versioned and can be rolled back if needed.

## Core Workflow

### Automatic Commit Process

After completing ANY code modification task, the AI MUST immediately:

1. **Stage Changes**
   ```bash
   git add -A
   ```

2. **Generate Commit Message**
   Create a descriptive commit message following this format:
   ```
   [filename or feature] - Action description
   ```
   
   Examples:
   - `[vite.config.js]` - Added proxy configuration for API routing
   - `[auth]` - Implemented JWT token validation middleware
   - `[ui]` - Fixed button hover state styling

3. **Commit Changes**
   ```bash
   git commit -m "[message]"
   ```

### Rollback Process

When user requests to rollback or the AI needs to undo changes:

1. **Find Target Commit**
   ```bash
   git log --oneline -10
   ```

2. **Hard Reset to Previous State**
   ```bash
   git reset --hard HEAD~1
   ```

3. **Confirm Rollback**
   - Show the rollback result to user
   - List remaining commits

## Usage Rules

**MUST commit after:**
- Creating new files
- Modifying existing code
- Deleting files
- Configuration changes
- Any file system modifications

**Before rollback, MUST:**
- Inform user about what will be rolled back
- Confirm the rollback target commit
- Explain the impact of hard reset

## Safety Guidelines

- Use `git reset --hard` ONLY when user explicitly requests rollback
- Always generate meaningful commit messages that describe the actual changes
- Commit frequently to maintain granular history
- Before hard reset, ensure uncommitted work is either committed or intentionally discarded
