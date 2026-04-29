import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def collections_installed():
    requirements = ROOT / "requirements.yml"
    if not requirements.exists():
        return
    subprocess.run(
        ["ansible-galaxy", "collection", "install", "-r", str(requirements)],
        check=True,
    )


@pytest.fixture(scope="session")
def fake_inventory(tmp_path_factory):
    path = tmp_path_factory.mktemp("inv") / "hosts.ini"
    path.write_text("[windows]\nwin1\n\n[linux]\nlin1\n")
    return str(path)
