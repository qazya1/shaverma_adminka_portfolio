"""Renders the systemd unit file for a newly provisioned shaverma
backend instance.

Deliberately does NOT include `--reload` on uvicorn's ExecStart (unlike
the hand-written template this was based on) -- that's a dev-only file
watcher flag with no place in a production unit; existing, manually
created services are untouched either way, this only affects units this
wizard writes.
"""

_UNIT_TEMPLATE = """\
[Unit]
Description={system_name} Backend
After=network.target

[Service]
User={work_user}
Group={work_user}
WorkingDirectory={instance_dir}/backend
Environment="PATH={venv_dir}/bin"
ExecStart={venv_dir}/bin/uvicorn app.main:app --host 127.0.0.1 --port {port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def render_unit(system_name: str, work_user: str, venv_dir: str, instance_dir: str, port: int) -> str:
    return _UNIT_TEMPLATE.format(
        system_name=system_name,
        work_user=work_user,
        venv_dir=venv_dir.rstrip("/"),
        instance_dir=instance_dir.rstrip("/"),
        port=port,
    )
