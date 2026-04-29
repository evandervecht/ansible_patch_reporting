import shlex
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def render(name: str, variables: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        keep_trailing_newline=True,
    )
    # Mirror Ansible's `quote` filter (shlex.quote) so templates that depend
    # on it render identically under test as they do under Ansible.
    env.filters["quote"] = shlex.quote
    return env.get_template(name).render(**variables)


def test_windows_template_renders():
    out = render(
        "patch_check.ps1.j2",
        {
            "output_file_windows": r"C:\tmp\patches.txt",
            "api_base_url": "https://api.example.com",
        },
    )
    assert r"C:\tmp\patches.txt" in out
    assert "https://api.example.com" in out
    assert "/api/ingest/patches/windows?hostname=" in out
    assert "Get-HotFix" in out
    assert "Invoke-RestMethod" in out


def test_windows_template_is_hardened():
    """Hostname URL-encoded, request has timeout, no BOM, ACL locked down."""
    out = render(
        "patch_check.ps1.j2",
        {
            "output_file_windows": r"C:\tmp\patches.txt",
            "api_base_url": "http://api:8052",
        },
    )
    assert "[uri]::EscapeDataString($hostnameVal)" in out
    assert "-TimeoutSec" in out
    assert "UTF8Encoding" in out and "$false" in out  # BOM-less UTF-8
    assert "icacls" in out
    assert "NT AUTHORITY\\SYSTEM" in out


def test_linux_template_renders():
    out = render(
        "patch_check.sh.j2",
        {
            "output_file_linux": "/tmp/patches.txt",
            "api_base_url": "https://api.example.com",
        },
    )
    assert "/tmp/patches.txt" in out
    assert "https://api.example.com" in out
    assert "/api/ingest/patches/linux?hostname=" in out
    assert "/etc/os-release" in out
    assert "curl" in out
    assert "--data-binary" in out


def test_linux_template_is_hardened():
    """umask 0077, urlencode helper, curl timeouts + --fail-with-body."""
    out = render(
        "patch_check.sh.j2",
        {
            "output_file_linux": "/tmp/patches.txt",
            "api_base_url": "http://api:8052",
        },
    )
    assert "umask 077" in out
    assert "urlencode" in out
    assert "--connect-timeout" in out
    assert "--max-time" in out
    assert "--fail-with-body" in out


def test_setup_template_inlines_patch_check_and_cron_entry():
    out = render(
        "setup.sh.j2",
        {
            "task_user_linux": "root",
            "output_dir_linux": "/var/lib/patch_check",
            "output_file_linux": "/var/lib/patch_check/patches.txt",
            "script_path_linux": "/usr/local/bin/patch_check.sh",
            "api_base_url": "http://api:8052",
            "schedule_hour": 2,
            "schedule_minute": 0,
        },
    )
    # bootstrap directives
    assert "mkdir -p" in out
    assert "/var/lib/patch_check" in out
    assert "/usr/local/bin/patch_check.sh" in out
    # cron entry written into /etc/cron.d
    assert "/etc/cron.d/patch_check" in out
    assert "0 2 * * * $TASK_USER $SCRIPT_PATH" in out
    # included patch_check.sh body is inlined verbatim
    assert "/etc/os-release" in out
    assert "/api/ingest/patches/linux?hostname=" in out
    assert "curl" in out
    # heredoc must use the single-quoted form so the inner ${VARS} survive
    assert "<<'PATCH_CHECK_SCRIPT_EOF'" in out


def test_setup_template_locks_down_permissions_and_quotes_vars():
    """Output dir + script chmod 0700, vars use Jinja `| quote` filter."""
    out = render(
        "setup.sh.j2",
        {
            # An adversarial value: contains a single quote that would break
            # naive quoting and let the rest of the value run as shell.
            "task_user_linux": "ro'ot",
            "output_dir_linux": "/var/lib/patch_check",
            "output_file_linux": "/var/lib/patch_check/patches.txt",
            "script_path_linux": "/usr/local/bin/patch_check.sh",
            "api_base_url": "http://api:8052",
            "schedule_hour": 2,
            "schedule_minute": 0,
        },
    )
    assert "umask 077" in out
    # 0700 not 0755 on dir + script
    assert "chmod 0700 \"$OUTPUT_DIR\"" in out
    assert "chmod 0700 \"$SCRIPT_PATH\"" in out
    # /etc/cron.d entry stays 0644 root-owned (cron requires this)
    assert "chmod 0644 \"$CRON_FILE\"" in out
    # The single quote in task_user_linux must have been escaped, not passed
    # through verbatim — i.e. the value never appears as-is in the output.
    assert "'ro'ot'" not in out
    assert "ro'\"'\"'ot" in out  # how Jinja's `quote` filter escapes a `'`
