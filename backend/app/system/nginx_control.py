"""Business-logic layer between the API and the ActionRegistry for the
shared nginx config file.

    API -> NginxControlService -> ActionRegistry -> CommandExecutor -> Ubuntu -> nginx_config_helper.py

Nginx corrupting the *shared* config would take down every provisioned
site at once, not just the one being added -- so `upsert_service_block`
never writes a change without validating it first, and automatically
writes the previous content back if `nginx -t` rejects the new one.
"""

from dataclasses import dataclass

from app.provisioning.nginx_template import upsert_block
from app.system.exceptions import SystemExecutionError
from app.system.registry import ActionRegistry


class NginxConfigInvalidError(SystemExecutionError):
    """Raised when the new config failed `nginx -t`. The previous config
    has already been restored by the time this is raised."""

    def __init__(self, nginx_test_output: str) -> None:
        super().__init__(f"nginx -t rejected the new config (rolled back): {nginx_test_output.strip()}")
        self.nginx_test_output = nginx_test_output


@dataclass(frozen=True)
class NginxUpsertResult:
    config_text: str


class NginxControlService:
    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    async def read_config(self) -> str:
        action = self._get_action("nginx.read_config")
        result = await action.run()
        if result.exit_code == 0:
            return result.stdout
        if result.exit_code == 3:  # config file doesn't exist yet
            return ""
        raise SystemExecutionError(
            f"nginx_config_helper.py read failed (exit {result.exit_code}): {result.stderr.strip()}"
        )

    async def upsert_service_block(self, system_name: str, new_block: str) -> NginxUpsertResult:
        """Insert/replace `system_name`'s block, validate with `nginx
        -t`, and only then reload nginx. On validation failure, the
        previous config is written back before raising."""

        previous_config = await self.read_config()
        new_config = upsert_block(previous_config, system_name, new_block)

        await self._write_config(new_config)

        test_result = await self._get_action("nginx.test").run()
        if test_result.exit_code != 0:
            # Auto-rollback -- never leave a broken config live, even
            # briefly.
            await self._write_config(previous_config)
            raise NginxConfigInvalidError(test_result.stderr or test_result.stdout)

        reload_result = await self._get_action("nginx.reload").run()
        if reload_result.exit_code != 0:
            raise SystemExecutionError(f"systemctl reload nginx failed: {reload_result.stderr.strip()}")

        return NginxUpsertResult(config_text=new_config)

    async def _write_config(self, content: str) -> None:
        action = self._get_action("nginx.write_config")
        result = await action.run(content=content.encode("utf-8"))
        if result.exit_code != 0:
            raise SystemExecutionError(f"nginx_config_helper.py write failed: {result.stderr.strip()}")

    def _get_action(self, name: str):
        action = self._registry.get(name)
        if action is None:
            raise SystemExecutionError(f"required system action is not registered: {name}")
        return action
