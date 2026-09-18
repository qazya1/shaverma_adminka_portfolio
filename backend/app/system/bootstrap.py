"""Wires the complete, reviewed set of production system actions into
the ActionRegistry. This is the one place in the codebase where real
administrative capability is switched on.

Called once at application startup (see app/main.py). If an action name
is already registered (e.g. called twice), `ActionRegistry.register`
raises rather than silently no-opping.
"""

from app.core.config import Settings
from app.system.env_actions import EnvReadAction, EnvWriteAction
from app.system.executor import CommandExecutor
from app.system.instance_actions import (
    InstanceCreateTreeAction,
    InstanceInstallBackendAction,
    InstanceInstallDistAction,
)
from app.system.nginx_actions import NginxReadConfigAction, NginxReloadAction, NginxTestAction, NginxWriteConfigAction
from app.system.registry import ActionRegistry
from app.system.seed_actions import SeedListAction, SeedReadDataAction, SeedRunDbAction, SeedWriteDataAction
from app.system.service_actions import (
    ServiceEnableNowAction,
    ServiceStartAction,
    ServiceStatusAction,
    ServiceStopAction,
)
from app.system.systemd_actions import SystemdWriteUnitAction


def register_default_actions(registry: ActionRegistry, settings: Settings, executor: CommandExecutor) -> None:
    timeout = settings.system_command_timeout_seconds
    output_limit = settings.system_command_output_limit_bytes

    registry.register(ServiceStatusAction(executor, settings.systemctl_path, timeout, output_limit))
    registry.register(ServiceStartAction(executor, settings.systemctl_path, settings.sudo_path, timeout, output_limit))
    registry.register(ServiceStopAction(executor, settings.systemctl_path, settings.sudo_path, timeout, output_limit))
    registry.register(
        ServiceEnableNowAction(executor, settings.systemctl_path, settings.sudo_path, timeout, output_limit)
    )

    registry.register(EnvReadAction(executor, settings.env_helper_path, settings.sudo_path, timeout, output_limit))
    registry.register(EnvWriteAction(executor, settings.env_helper_path, settings.sudo_path, timeout, output_limit))

    registry.register(InstanceCreateTreeAction(executor, settings.instance_files_helper_path, settings.sudo_path, timeout))
    registry.register(
        InstanceInstallBackendAction(executor, settings.instance_files_helper_path, settings.sudo_path, timeout)
    )
    registry.register(
        InstanceInstallDistAction(executor, settings.instance_files_helper_path, settings.sudo_path, timeout)
    )

    registry.register(NginxReadConfigAction(executor, settings.nginx_config_helper_path, settings.sudo_path, timeout))
    registry.register(NginxWriteConfigAction(executor, settings.nginx_config_helper_path, settings.sudo_path, timeout))
    registry.register(NginxTestAction(executor, settings.nginx_binary_path, settings.sudo_path, timeout))
    registry.register(NginxReloadAction(executor, settings.systemctl_path, settings.sudo_path, timeout))

    registry.register(SystemdWriteUnitAction(executor, settings.systemd_unit_helper_path, settings.sudo_path, timeout))

    registry.register(SeedListAction(executor, settings.seed_helper_path, settings.sudo_path, timeout, output_limit))
    registry.register(
        SeedReadDataAction(executor, settings.seed_helper_path, settings.sudo_path, timeout, output_limit)
    )
    registry.register(
        SeedWriteDataAction(executor, settings.seed_helper_path, settings.sudo_path, timeout, output_limit)
    )
    registry.register(
        SeedRunDbAction(
            executor,
            settings.seed_helper_path,
            settings.sudo_path,
            timeout,
            output_limit,
            settings.seed_run_timeout_seconds,
        )
    )
