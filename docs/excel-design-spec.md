# Excel Design Specification

This document defines the standard Excel migration design workbook for DataMapX.

## 1. Purpose

The workbook is a design input, not an execution format.
It is used to describe one project that may generate multiple `merge.yml` and `migration.yml` files, plus the scripts and manifest needed to run them in order.

The workbook is intentionally structured and does not accept free-form layout.
DataMapX reads the design, validates it, generates YAML, and then reuses the existing CLI execution engine.

## 2. Workbook Model

The standard workbook is composed of a small set of sheets.
Each detailed sheet is linked to a job through `job_id`.

Required sheets:

- `project`
- `jobs`
- `merge_inputs`
- `merge_rules`
- `migration_inputs`
- `input_schema`
- `references`
- `reference_schema`
- `derived`
- `outputs`
- `mappings`
- `validations`
- `filters`
- `checks`
- `error_handling`
- `runtime`

## 3. Job Model

The `jobs` sheet defines the execution graph.

Required columns:

- `job_id`
- `job_type`
- `order`
- `enabled`
- `config_name`

Optional columns:

- `description`
- `depends_on`

Rules:

- `job_type` is `merge` or `migration`
- `order` defines the default generation order
- `depends_on` contains comma-separated `job_id` values
- disabled jobs are skipped
- `config_name` becomes the generated YAML file name stem

The workbook may define many jobs.
Complex migrations are modeled as multiple merge and migration jobs linked by dependencies.

## 4. Sheet Responsibilities

`project`

- project metadata such as name and description

`merge_inputs`

- input files for merge jobs
- input role, path, delimiter, encoding, header, and key

`merge_rules`

- merge output columns and merge behavior

`migration_inputs`

- input files for migration jobs

`input_schema`

- schema settings for migration input columns

`references`

- reference CSV definitions for migration jobs

`reference_schema`

- schema settings for reference columns

`derived`

- derived field definitions for migration jobs

`outputs`

- output file definitions and output column order

`mappings`

- output column rules for migration jobs

`validations`

- input and output validation rules

`filters`

- include and exclude filter rules

`checks`

- run-level checks

`error_handling`

- row-level error policy and report targets

`runtime`

- run id and summary/log settings

## 5. Output Artifacts

A successful conversion produces:

- `configs/*.yml`
- `scripts/run_all.sh`
- `scripts/run_all.bat`
- `manifest.json`
- `design-summary.json`
- `design-errors.csv`

The generated scripts execute the generated YAML files in dependency order.
The manifest records the same order and the command line for each job.

## 6. Validation Rules

The workbook must be validated before YAML generation.

Required checks:

- `job_id` values are unique
- `job_type` values are supported
- `order` values are not ambiguous
- `depends_on` references existing jobs
- no dependency cycles exist
- every detail row points to a known `job_id`
- merge jobs contain the merge sheets they need
- migration jobs contain the migration sheets they need
- generated YAML passes the existing `validate-config` or merge config validation

Validation errors must include the sheet name, row number, and column name.

## 7. Template Example

The repository includes a CSV-based sheet sample under `examples/08_excel_design/`.
That sample mirrors this specification and is meant to be a reference for the future Excel parser implementation.

## 8. Assumptions

- Standard Excel workbook format only
- No free-form worksheet layouts
- No direct CSV-to-CSV execution from Excel
- Existing YAML execution semantics remain the source of truth
- `merge` and `migration` jobs may coexist in one workbook
