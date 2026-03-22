"""
Workflow registry — maps workflow names to classes.
Why: Celery tasks resolve workflows by name (string).
The registry is the single place to register new workflows.
Adding a workflow = one line here.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workflow import Workflow

_REGISTRY: dict[str, type["Workflow"]] = {}


def register(name: str):
    """
    Decorator to register a workflow class.

    Usage:
        @register("my_workflow")
        class MyWorkflow(Workflow):
            ...
    """
    def decorator(cls: type["Workflow"]) -> type["Workflow"]:
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_workflow(name: str) -> type["Workflow"]:
    """
    Resolve a workflow class by name.
    Raises ValueError with helpful message if not found.
    """
    if name not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise ValueError(
            f"Workflow '{name}' not found. "
            f"Available workflows: {available}"
        )
    return _REGISTRY[name]


def list_workflows() -> list[str]:
    """Return all registered workflow names."""
    return list(_REGISTRY.keys())