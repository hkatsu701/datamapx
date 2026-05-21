# Agent Workflow

This document defines the recommended multi-agent development workflow for DataMapX.

The goal is to keep planning, implementation, and verification separated so that changes stay small, testable, and easier to review.

## Roles

| Role | Recommended model | Mode | Responsibility |
| --- | --- | --- | --- |
| PM | `gpt-5.5` | Plan mode | Clarify requirements, produce implementation plans, manage roadmap and scope. |
| Developer | `gpt-5.4-mini` | Default mode | Implement the approved plan, add focused tests, update docs. |
| QA | `gpt-5.4` | Default mode | Review implementation, run tests, check docs/spec alignment, identify release risk. |
| Release | `gpt-5.4-mini` or current Developer | Default mode | Final status check, commit, tag, and push when requested. |

## Manual Switching

Codex mode and model selection are controlled by the user interface. DataMapX cannot switch them automatically from inside the repository.

Use this manual flow:

1. Planning request
   - Switch model to `gpt-5.5`.
   - Enable Plan mode.
   - Ask PM to create or revise the implementation plan.
   - PM must finish with a complete `<proposed_plan>` block.

2. Implementation request
   - Switch model to `gpt-5.4-mini`.
   - Disable Plan mode.
   - Ask Developer to implement the approved plan.
   - Developer must keep changes small, add tests, update docs, and report verification results.

3. QA request
   - Switch model to `gpt-5.4`.
   - Keep Plan mode disabled.
   - Ask QA to review the latest diff and run verification.
   - QA should lead with findings. If no issues are found, it should say so clearly.

4. Release request
   - Keep Plan mode disabled.
   - Use the Developer or QA model.
   - Run final checks, then commit and push only when explicitly requested.

## Cycle

Each task should follow this cycle:

1. PM creates a decision-complete implementation plan.
2. User approves the plan.
3. Developer implements only that plan.
4. Developer runs focused tests and updates documentation.
5. QA reviews the diff, tests, and docs.
6. Developer fixes QA findings when needed.
7. Release performs final checks and pushes when requested.

## Handoff Rules

- PM must not implement code.
- Developer must not silently expand scope beyond the approved plan.
- QA must not rewrite the implementation unless explicitly asked; it should identify issues and verify behavior.
- Release must not push unverified or unrelated changes.
- Every behavior change must include tests and documentation updates when user-facing behavior changes.

## Task Size

Prefer small iterations:

- One feature or one behavioral correction per task.
- One clear test group per task.
- Documentation updated in the same task.
- No Excel design import work should begin until the CLI execution engine roadmap is stable.

## Checklists

Use these role-specific checklists:

- [PM checklist](pm-checklist.md)
- [Developer checklist](developer-checklist.md)
- [QA checklist](qa-checklist.md)
- [Release checklist](release-checklist.md)
