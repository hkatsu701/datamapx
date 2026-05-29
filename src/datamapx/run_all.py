"""Run-all configuration loading for datamapx."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from datamapx.config import ProjectConfig, StrictModel
from datamapx.exceptions import ConfigError


class RunAllJobConfig(StrictModel):
    """One job entry in a run-all YAML file."""

    name: str
    type: Literal["run", "merge", "union", "unpivot", "aggregate"]
    config: str
    reports_dir: str | None = None
    html_report: bool = False

    @field_validator("name", "config", "reports_dir")
    @classmethod
    def validate_non_empty_paths(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class RunAllConfig(StrictModel):
    """Top-level run-all YAML model."""

    version: Literal[1]
    project: ProjectConfig
    jobs: list[RunAllJobConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_run_all_consistency(self) -> RunAllConfig:
        errors: list[str] = []
        if not self.jobs:
            errors.append("jobs: run-all requires at least one job")

        seen_names: set[str] = set()
        for index, job in enumerate(self.jobs):
            if job.name in seen_names:
                errors.append(f"jobs[{index}].name: duplicate job name '{job.name}'")
            seen_names.add(job.name)

        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_run_all_config(path: str | Path) -> RunAllConfig:
    """Load and validate a run-all YAML config."""

    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{config_path}: cannot read config file: {exc}") from exc

    if raw_config is None:
        raise ConfigError(f"{config_path}: config file is empty")
    if not isinstance(raw_config, dict):
        raise ConfigError(f"{config_path}: top-level YAML value must be a mapping")

    try:
        return RunAllConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def resolve_run_all_path(path: str, base_path: Path) -> Path:
    """Resolve a path relative to the run-all YAML file."""

    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return base_path / resolved


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
