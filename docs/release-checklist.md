# Release Checklist

Use this checklist before committing, tagging, or pushing DataMapX changes.

Recommended setup:

- Model: `gpt-5.4-mini` or `gpt-5.4`
- Mode: Default mode

## Final Checks

Run:

```bash
git status --short
pytest
ruff check .
```

Review:

- Changed files are expected.
- No generated scratch files are included.
- README and docs are consistent with behavior.
- Examples still match documented commands.

## Commit Rules

- Commit only when the user explicitly requests it.
- Do not include unrelated user changes.
- Use a concise commit message that describes behavior, not implementation noise.

## Push Rules

- Push only when the user explicitly requests it.
- Report the branch and commit hash after pushing.

## Exit Criteria

Release work is complete when:

- Final verification has passed.
- Commit and push status is clear.
- Any uncommitted or unpushed changes are explicitly reported.
