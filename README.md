# patch-upload

Ansible automation that schedules a recurring patch-info collector on each managed host
and uploads the result to an ingest API.

- **Windows hosts** get a Windows Scheduled Task that runs a PowerShell script as a
  configurable user (default `SYSTEM`).
- **Linux hosts** get a cron entry that runs a bash script as a configurable user
  (default `root`).

**Managed hosts do not need Python.** Python is only required on the controller
(your local machine / CI runner) to run `ansible-core`, `pytest`, and `ansible-lint`.

- Windows: WinRM + PowerShell modules (`ansible.windows.*`, `community.windows.*`) —
  no Python on target.
- Linux: a bootstrap script is rendered locally and shipped to the target via
  Ansible's `script` module, which only needs POSIX shell. The cron entry is
  installed into `/etc/cron.d/patch_check` by the bootstrap.

Each script collects host + patch information, writes it as raw text to an output file,
and POSTs the file to:

```
{{ api_base_url }}/api/ingest/patches/{windows|linux}?hostname=<hostname>
```

## What gets collected

| OS      | Commands                                                                 |
| ------- | ------------------------------------------------------------------------ |
| Windows | `hostname`, `Get-HotFix`                                                 |
| Linux   | `hostname`, `/etc/os-release`, `apt-get -s upgrade` / `dnf check-update` / `yum check-update` |

Upload mechanism:

- Windows: `Invoke-RestMethod -Method Post -ContentType 'text/plain' -InFile <file>`
- Linux: `curl -X POST -H "Content-Type: text/plain" --data-binary @<file>`

## Project layout

```
.
├── playbook.yml                 # two plays: windows + linux
├── templates/
│   ├── patch_check.ps1.j2       # PowerShell collector script (Windows)
│   ├── patch_check.sh.j2        # bash collector script (Linux)
│   └── setup.sh.j2              # bootstrap that installs the script + cron entry
├── requirements.yml             # ansible.windows + community.windows collections
├── pyproject.toml               # uv-managed dev deps (pytest, ansible-core, ansible-lint, ...)
├── .ansible-lint
└── tests/
    ├── conftest.py
    ├── test_templates.py        # Jinja render checks
    └── test_playbook.py         # syntax-check + ansible-lint
```

## Variables

Defaults live in `playbook.yml`. Override per-host or via group_vars / extra-vars.

### Windows play

| Variable               | Default                                       |
| ---------------------- | --------------------------------------------- |
| `task_user_windows`    | `SYSTEM`                                      |
| `api_base_url`         | `http://api:8052`                             |
| `script_dir_windows`   | `C:\ProgramData\patch_check`                  |
| `script_path_windows`  | `C:\ProgramData\patch_check\patch_check.ps1`  |
| `output_file_windows`  | `C:\ProgramData\patch_check\patches.txt`      |
| `schedule_hour`        | `2`                                           |
| `schedule_minute`      | `0`                                           |

### Linux play

| Variable             | Default                            |
| -------------------- | ---------------------------------- |
| `task_user_linux`    | `root`                             |
| `api_base_url`       | `http://api:8052`                  |
| `script_path_linux`  | `/usr/local/bin/patch_check.sh`    |
| `output_dir_linux`   | `/var/lib/patch_check`             |
| `output_file_linux`  | `/var/lib/patch_check/patches.txt` |
| `schedule_hour`      | `2`                                |
| `schedule_minute`    | `0`                                |

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for Python tooling. Do **not** use
`pip` — `uv sync` manages the venv and keeps dependencies pinned via `uv.lock`.

```bash
# 1. install dev tools (ansible-core, ansible-lint, pytest, ...)
uv sync --group dev

# 2. install required Ansible collections into the uv-managed venv
uv run ansible-galaxy collection install -r requirements.yml
```

## Inventory example

```ini
# inventory.ini
[windows]
win-host-01 ansible_user=Administrator ansible_password=... ansible_connection=winrm

[linux]
lin-host-01 ansible_user=ubuntu

[windows:vars]
task_user_windows=SYSTEM
api_base_url=https://patch-api.example.com

[linux:vars]
task_user_linux=root
api_base_url=https://patch-api.example.com
```

## Running the playbook

```bash
# dry run
uv run ansible-playbook -i inventory.ini playbook.yml --check

# apply
uv run ansible-playbook -i inventory.ini playbook.yml

# override a variable on the fly
uv run ansible-playbook -i inventory.ini playbook.yml \
    -e api_base_url=https://patch-api.example.com \
    -e schedule_hour=4
```

## Why no Python on managed hosts

Most Ansible modules execute by shipping a Python module to the target and running it
there. To avoid that requirement, this playbook restricts itself to:

- **Windows** — `ansible.windows.*` and `community.windows.*` modules, which are
  implemented in PowerShell and run via WinRM.
- **Linux** — only `ansible.builtin.script` runs against the target. The Linux play
  renders `templates/setup.sh.j2` (which `{% include %}`s `patch_check.sh.j2`) into a
  local temp file via `delegate_to: localhost`, then `script` ships and runs it on the
  target through SSH. `gather_facts` is disabled for the same reason. The result: the
  target needs only `bash`, `cron`, and `curl`.

## Tests

All tests run through uv:

```bash
uv run pytest                 # run everything
uv run pytest -k templates    # template render checks only
uv run ansible-lint           # ad-hoc lint pass
```

What the tests cover:

- `tests/test_templates.py` — renders both Jinja2 templates with sample variables and
  asserts the output contains the expected URL, file paths, and commands.
- `tests/test_playbook.py` — runs `ansible-playbook --syntax-check` and `ansible-lint`
  against `playbook.yml`. The session fixture installs the Ansible collections from
  `requirements.yml` automatically.

## Manual one-off run (without Ansible)

The scripts are plain Jinja2 templates over POSIX shell / PowerShell, so once rendered
they can be invoked directly. After Ansible deploys them:

```powershell
# Windows
PowerShell -ExecutionPolicy Bypass -File C:\ProgramData\patch_check\patch_check.ps1
```

```bash
# Linux
sudo /usr/local/bin/patch_check.sh
```

## License

[MIT](LICENSE) © Ellert van der Vecht
