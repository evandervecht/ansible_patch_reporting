from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def render(name: str, variables: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        keep_trailing_newline=True,
    )
    return env.get_template(name).render(**variables)


def test_windows_template_renders():
    out = render(
        "patch_check.ps1.j2",
        {
            "output_file_windows": r"C:\tmp\patches.txt",
            "api_base_url": "http://api:8052",
        },
    )
    assert r"C:\tmp\patches.txt" in out
    assert "http://api:8052/api/ingest/patches/windows?hostname=" in out
    assert "Get-HotFix" in out
    assert "Invoke-RestMethod" in out


def test_linux_template_renders():
    out = render(
        "patch_check.sh.j2",
        {
            "output_file_linux": "/tmp/patches.txt",
            "api_base_url": "http://api:8052",
        },
    )
    assert "/tmp/patches.txt" in out
    assert "http://api:8052/api/ingest/patches/linux?hostname=" in out
    assert "/etc/os-release" in out
    assert "curl" in out
    assert "--data-binary" in out


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
    assert "http://api:8052/api/ingest/patches/linux?hostname=" in out
    assert "curl" in out
    # heredoc must use the single-quoted form so the inner ${VARS} survive
    assert "<<'PATCH_CHECK_SCRIPT_EOF'" in out
