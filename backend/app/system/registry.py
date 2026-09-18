"""Action registry.

This defines the shape that system actions (`service.status`,
`service.start`, `service.stop`, `env.read`, `env.write`, and later e.g.
`deploy.run`, `logs.read`, ...) plug into. The registry class itself
stays generic and knows nothing about systemd, .env files, or any other
concrete capability -- concrete actions live in their own reviewed
modules (see app.system.service_actions, app.system.env_actions) and are
registered into the process-wide `registry` below via an explicit
`register_default_actions()` call (app.system.bootstrap) at startup
(app/main.py), never auto-discovered.

There is deliberately no generic `execute(command: str)` entry point
exposed anywhere in the API -- every action is an explicit, named,
individually-reviewed `SystemAction` implementation, not an arbitrary
command string accepted from a caller.
"""

from typing import Protocol, runtime_checkable

from app.system.models import CommandResult


@runtime_checkable
class SystemAction(Protocol):
    """Contract a future system action must satisfy.

    `name` is the stable identifier used to look the action up in the
    registry (e.g. "service.restart"). `run` performs the action and
    returns a structured result -- concrete actions will typically build
    a `CommandSpec` internally and delegate to `CommandExecutor`.
    """

    name: str

    async def run(self, **kwargs: object) -> CommandResult: ...


class ActionRegistry:
    """A simple name -> SystemAction lookup table.

    Intentionally minimal: no auto-discovery, no dynamic loading from
    config. Actions are registered explicitly in code, one line each, so
    the full set of things this service is capable of doing to the
    server is always visible by reading this module's (currently empty)
    call sites.
    """

    def __init__(self) -> None:
        self._actions: dict[str, SystemAction] = {}

    def register(self, action: SystemAction) -> None:
        if action.name in self._actions:
            raise ValueError(f"action already registered: {action.name}")
        self._actions[action.name] = action

    def get(self, name: str) -> SystemAction | None:
        return self._actions.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._actions.keys())


# Process-wide registry instance, populated at startup by
# app.system.bootstrap.register_default_actions().
registry = ActionRegistry()
