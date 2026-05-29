"""Aggregate pipeline for datamapx."""

from datamapx.aggregate.config import AggregateConfig, load_aggregate_config
from datamapx.aggregate.runner import AggregateResult, run_aggregate_pipeline

__all__ = [
    "AggregateConfig",
    "AggregateResult",
    "load_aggregate_config",
    "run_aggregate_pipeline",
]
