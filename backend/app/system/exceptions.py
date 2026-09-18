"""Exceptions raised by the system command execution layer."""


class SystemExecutionError(Exception):
    """Base class for all system-execution errors."""


class CommandTimeoutError(SystemExecutionError):
    """Raised when a command exceeds its allotted timeout and had to be
    killed."""


class OutputLimitExceededError(SystemExecutionError):
    """Raised when a command's stdout/stderr exceeded the configured
    byte limit and the process was terminated as a result."""


class InvalidSystemNameError(SystemExecutionError):
    """Raised when a services.system_name value is not a safe systemd
    unit identifier (see app.system.service_control.unit_name_for)."""


class ServiceNotFoundError(SystemExecutionError):
    """Raised when the target systemd unit does not exist on the host
    (systemctl reports LoadState=not-found)."""

    def __init__(self, unit_name: str) -> None:
        super().__init__(f"systemd unit not found: {unit_name}")
        self.unit_name = unit_name
