# Developer Checklist

Use this checklist when implementing an approved DataMapX plan.

Recommended setup:

- Model: `gpt-5.4-mini`
- Mode: Default mode

## Before Editing

- Read the approved plan.
- Inspect the relevant source, tests, and docs.
- Check current git status.
- Do not revert unrelated user changes.

## During Implementation

- Keep the change scoped to the approved plan.
- Follow existing project patterns.
- Add or update focused tests with the implementation.
- Update docs in the same change when behavior changes.
- Keep CLI output and error messages understandable for non-engineers.

## Verification

Run at least:

```bash
pytest
ruff check .
```

For CLI behavior changes, also run targeted CLI tests or examples.

## Exit Criteria

Developer work is complete when:

- The approved behavior is implemented.
- Tests cover normal, error, and boundary cases where relevant.
- Documentation matches the implementation.
- Verification commands and results are reported.
- Remaining risks or skipped checks are explicitly stated.
