"""Renders the nginx server{} blocks for one shaverma instance, and
inserts/replaces them in the shared config file's text idempotently --
re-running the nginx provisioning step must update the existing block
in place, never pile up a duplicate.

All pure string manipulation here; no filesystem or subprocess access at
all. See app.system.nginx_control for the layer that actually reads the
live config, calls this, writes it back, and validates with `nginx -t`.
"""

import re

_MARKER_BEGIN = "# adminka:service:{system_name}:begin"
_MARKER_END = "# adminka:service:{system_name}:end"

_BLOCK_TEMPLATE = """\
{marker_begin}
# front
server {{
    listen 443 ssl http2;
    ssl_certificate     {ssl_certificate};
    ssl_certificate_key {ssl_certificate_key};

    server_name {frontend_domain};

    location / {{
        root {dist_root};
    }}
}}

# back
server {{
    listen 443 ssl http2;
    ssl_certificate     {ssl_certificate};
    ssl_certificate_key {ssl_certificate_key};

    server_name {backend_domain};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
{marker_end}"""


def render_block(
    system_name: str,
    frontend_domain: str,
    backend_domain: str,
    dist_root: str,
    port: int,
    ssl_certificate: str,
    ssl_certificate_key: str,
) -> str:
    return _BLOCK_TEMPLATE.format(
        marker_begin=_MARKER_BEGIN.format(system_name=system_name),
        marker_end=_MARKER_END.format(system_name=system_name),
        frontend_domain=frontend_domain,
        backend_domain=backend_domain,
        dist_root=dist_root,
        port=port,
        ssl_certificate=ssl_certificate,
        ssl_certificate_key=ssl_certificate_key,
    )


def _block_pattern(system_name: str) -> re.Pattern[str]:
    begin = re.escape(_MARKER_BEGIN.format(system_name=system_name))
    end = re.escape(_MARKER_END.format(system_name=system_name))
    return re.compile(rf"{begin}.*?{end}\n?", re.DOTALL)


def has_block(config_text: str, system_name: str) -> bool:
    return _block_pattern(system_name).search(config_text) is not None


def upsert_block(config_text: str, system_name: str, new_block: str) -> str:
    """Replace this system_name's existing block in place if present,
    otherwise append it (separated by a blank line from whatever's
    already there)."""

    pattern = _block_pattern(system_name)
    if pattern.search(config_text):
        return pattern.sub(new_block + "\n", config_text, count=1)

    if config_text and not config_text.endswith("\n"):
        config_text += "\n"
    separator = "\n" if config_text else ""
    return f"{config_text}{separator}{new_block}\n"


def remove_block(config_text: str, system_name: str) -> str:
    return _block_pattern(system_name).sub("", config_text)
