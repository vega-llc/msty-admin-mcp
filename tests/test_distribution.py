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


def test_package_version_and_operator_commands_are_current():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    installed_check = (ROOT / "scripts/check_installed.py").read_text(encoding="utf-8")

    assert 'version = "1.1.1"' in pyproject
    assert 'msty-local-ops-doctor = "msty_ops.doctor:main"' in pyproject
    assert 'msty-local-ops-support = "msty_ops.support:main"' in pyproject
    assert 'serverInfo.version == "1.1.1"' in installed_check


def test_release_tag_must_match_project_version():
    valid = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_release_tag.py"), "v1.1.1"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    invalid = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_release_tag.py"), "v1.1"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert valid.returncode == 0
    assert invalid.returncode == 1


def test_release_metadata_contains_sbom_provenance_and_checksums(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "package.whl").write_bytes(b"synthetic wheel")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "mcp==1.29.0 \\\n    --hash=sha256:abc\n" "psutil==7.0.0 \\\n    --hash=sha256:def\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_release_metadata.py"),
            "--dist",
            str(dist),
            "--requirements",
            str(requirements),
            "--version",
            "1.1.1",
        ],
        check=True,
    )

    sbom = json.loads((dist / "msty-local-ops.cdx.json").read_text(encoding="utf-8"))
    provenance = json.loads((dist / "provenance.json").read_text(encoding="utf-8"))
    checksums = (dist / "SHA256SUMS").read_text(encoding="utf-8")
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert {item["name"] for item in sbom["components"]} == {"mcp", "psutil"}
    assert provenance["subject"]["version"] == "1.1.1"
    assert "package.whl" in checksums
    assert "msty-local-ops.cdx.json" in checksums
    assert "provenance.json" in checksums
