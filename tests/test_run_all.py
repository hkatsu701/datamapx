from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from datamapx.exceptions import ConfigError
from datamapx.run_all import load_run_all_config


def test_load_run_all_config_success(tmp_path: Path) -> None:
    config_path = _write_run_all_config(tmp_path)

    config = load_run_all_config(config_path)

    assert config.project.name == "run_all_sample"
    assert [job.name for job in config.jobs] == ["migration", "merge_stage", "union_stage"]
    assert [job.type for job in config.jobs] == ["run", "merge", "union"]
    assert config.jobs[0].html_report is True


def test_load_run_all_config_accepts_unpivot_job(tmp_path: Path) -> None:
    config_path = _write_run_all_config(
        tmp_path,
        jobs=[
            {
                "name": "unpivot_stage",
                "type": "unpivot",
                "config": "./unpivot.yml",
                "reports_dir": "./reports/unpivot",
                "html_report": True,
            }
        ],
    )

    config = load_run_all_config(config_path)

    assert [job.name for job in config.jobs] == ["unpivot_stage"]
    assert [job.type for job in config.jobs] == ["unpivot"]
    assert config.jobs[0].reports_dir == "./reports/unpivot"


def test_load_run_all_config_accepts_aggregate_job(tmp_path: Path) -> None:
    config_path = _write_run_all_config(
        tmp_path,
        jobs=[
            {
                "name": "aggregate_stage",
                "type": "aggregate",
                "config": "./aggregate.yml",
                "reports_dir": "./reports/aggregate",
                "html_report": False,
            }
        ],
    )

    config = load_run_all_config(config_path)

    assert [job.name for job in config.jobs] == ["aggregate_stage"]
    assert [job.type for job in config.jobs] == ["aggregate"]


def test_load_run_all_config_rejects_empty_jobs(tmp_path: Path) -> None:
    config_path = _write_run_all_config(tmp_path, jobs=[])

    with pytest.raises(ConfigError, match="run-all requires at least one job"):
        load_run_all_config(config_path)


def test_load_run_all_config_rejects_duplicate_job_names(tmp_path: Path) -> None:
    config_path = _write_run_all_config(
        tmp_path,
        jobs=[
            {
                "name": "job1",
                "type": "run",
                "config": "./run.yml",
            },
            {
                "name": "job1",
                "type": "merge",
                "config": "./merge.yml",
            },
        ],
    )

    with pytest.raises(ConfigError, match="duplicate job name"):
        load_run_all_config(config_path)


def test_load_run_all_config_rejects_unknown_job_type(tmp_path: Path) -> None:
    config_path = _write_run_all_config(
        tmp_path,
        jobs=[
            {
                "name": "job1",
                "type": "export",
                "config": "./run.yml",
            }
        ],
    )

    with pytest.raises(ConfigError, match="Input should be"):
        load_run_all_config(config_path)


def _write_run_all_config(
    tmp_path: Path,
    *,
    jobs: list[dict[str, object]] | None = None,
) -> Path:
    config_path = tmp_path / "run-all.yml"
    config = {
        "version": 1,
        "project": {"name": "run_all_sample"},
        "jobs": jobs
        if jobs is not None
        else [
            {
                "name": "migration",
                "type": "run",
                "config": "./run.yml",
                "reports_dir": "./reports/run",
                "html_report": True,
            },
            {
                "name": "merge_stage",
                "type": "merge",
                "config": "./merge.yml",
                "reports_dir": "./reports/merge",
                "html_report": False,
            },
            {
                "name": "union_stage",
                "type": "union",
                "config": "./union.yml",
                "reports_dir": "./reports/union",
                "html_report": False,
            },
        ],
    }
    rendered = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")
    return config_path
