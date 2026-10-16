"""Frozen synthetic workload registry; candidate execution is external only."""
from .registry import (
    TaskDefinition, inspect_candidate, linux_runner_request, list_tasks,
    load_task, materialize_task, tree_digest, trusted_control_report,
    validate_assets,
)

__all__ = ["TaskDefinition", "list_tasks", "load_task", "materialize_task",
           "validate_assets", "inspect_candidate", "tree_digest",
           "trusted_control_report", "linux_runner_request"]
