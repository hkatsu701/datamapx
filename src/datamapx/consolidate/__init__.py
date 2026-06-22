"""Consolidate pipeline for datamapx."""

from datamapx.consolidate.config import ConsolidateConfig, load_consolidate_config
from datamapx.consolidate.runner import ConsolidateResult, run_consolidate_pipeline

__all__ = [
    "ConsolidateConfig",
    "ConsolidateResult",
    "load_consolidate_config",
    "run_consolidate_pipeline",
]
