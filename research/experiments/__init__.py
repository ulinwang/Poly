"""Experiment orchestration: YAML config → calibrated sim → output/<exp_id>.

    from experiments.runner import run_experiment, load_config, compute_exp_id
    from experiments.config import ExperimentConfig
"""
from experiments.config import ExperimentConfig, parse_config
from experiments.runner import (
    compute_exp_id, load_config, run_experiment,
)

__all__ = [
    "ExperimentConfig", "parse_config",
    "compute_exp_id", "load_config", "run_experiment",
]
