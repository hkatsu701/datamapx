"""Merge pipeline for datamapx."""

from datamapx.merge.config import MergeConfig, load_merge_config
from datamapx.merge.runner import MergeResult, run_merge_pipeline
from datamapx.merge.wizard import MergeWizardResult, run_merge_wizard

__all__ = [
    "MergeConfig",
    "MergeResult",
    "MergeWizardResult",
    "load_merge_config",
    "run_merge_wizard",
    "run_merge_pipeline",
]
