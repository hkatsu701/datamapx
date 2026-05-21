# PM Checklist

Use this checklist when planning a DataMapX task.

Recommended setup:

- Model: `gpt-5.5`
- Mode: Plan mode

## Required Output

The PM must produce a complete `<proposed_plan>` block.

The plan must include:

- Clear goal and summary.
- In-scope behavior.
- Out-of-scope behavior.
- Public CLI/YAML/schema changes, if any.
- Implementation steps.
- Test plan.
- Documentation updates.
- Assumptions and defaults.

## Planning Rules

- Inspect the repository before finalizing a plan.
- Prefer small iterations over large feature batches.
- Avoid planning Excel design import work until the CLI execution engine task is stable.
- If the task changes CLI behavior, include `docs/cli-spec.md`.
- If the task changes YAML behavior, include `docs/config-spec.md`.
- If the task changes error behavior, include `docs/error-policy.md`.
- If the task changes user-facing workflow, include `README.md` and `README.ja.md`.

## Exit Criteria

PM work is complete when:

- The plan is decision-complete.
- The user can approve it without needing hidden implementation choices.
- The Developer can start coding without asking for additional design decisions.
