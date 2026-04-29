import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK = ROOT / "playbook.yml"


def test_playbook_syntax(collections_installed, fake_inventory):
    result = subprocess.run(
        [
            "ansible-playbook",
            "--syntax-check",
            "-i",
            fake_inventory,
            str(PLAYBOOK),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ansible_lint(collections_installed):
    result = subprocess.run(
        ["ansible-lint", str(PLAYBOOK)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    # 0 == clean; 2 == warnings (still acceptable under basic profile)
    assert result.returncode in (0, 2), result.stdout + result.stderr
