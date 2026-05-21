# QA Checklist

Use this checklist after Developer implementation.

Recommended setup:

- Model: `gpt-5.4`
- Mode: Default mode

## Review Focus

QA should review as a code reviewer, prioritizing:

- Behavioral regressions.
- Missing tests.
- Incorrect error handling.
- CLI/YAML spec drift.
- Documentation mismatch.
- Edge cases in migration data.
- Windows path and Japanese CSV usability where relevant.

## Verification

Run or confirm:

```bash
pytest
ruff check .
```

For CLI changes, run targeted command-level tests.

For docs-only changes, inspect links and terminology.

## Output Format

Lead with findings:

- If issues exist, list them by severity with file and line references.
- If no issues are found, say that clearly.
- Mention any residual risk or test gap.

## Exit Criteria

QA work is complete when:

- All relevant tests pass or failures are explained.
- Docs and implementation are consistent.
- Any remaining risks are known and acceptable.
- The task is ready for release or clearly returned to Developer.
