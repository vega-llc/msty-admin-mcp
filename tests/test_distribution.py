import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_public_boundary_scanner_passes_distribution():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_public_boundary.py"), str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_toolbox_config_writer_uses_explicit_python(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/write_toolbox_configs.py"),
            "--python",
            sys.executable,
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    paths = json.loads(completed.stdout)
    diagnostic = json.loads(Path(paths["diagnostic"]).read_text(encoding="utf-8"))
    local = json.loads(Path(paths["local_inference"]).read_text(encoding="utf-8"))

    assert diagnostic == {
        "command": str(Path(sys.executable).resolve()),
        "args": ["-m", "msty_ops.server"],
        "env": {"PYTHONUNBUFFERED": "1"},
    }
    assert local["args"] == ["-m", "msty_ops.local_server"]


def test_installer_selects_a_supported_python_before_the_default():
    installer = (ROOT / "Install Msty Local Ops.command").read_text(encoding="utf-8")

    assert "for candidate in python3.12 python3.11 python3.10 python3" in installer
    assert '"$PYTHON_BIN" -m venv "$VENV_DIR"' in installer
