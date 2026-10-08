import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).parents[1] / "scripts/install_skill.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    class Builder:
        def __init__(self, **kwargs):
            pass

        def create(self, runtime):
            binary = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            binary.parent.mkdir(parents=True)
            binary.write_text("simulated interpreter")

    monkeypatch.setattr(installer.venv, "EnvBuilder", Builder)
    monkeypatch.setattr(installer.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer.subprocess, "check_output", lambda *a, **k: installer.VERSION)
    wheel = tmp_path / f"autoreference-{installer.VERSION}-py3-none-any.whl"
    wheel.touch()
    return tmp_path / "installed", wheel


def test_install_update_and_preserve_user_files(installation):
    target, wheel = installation
    result = installer.install(target, wheel=wheel)
    assert result["version"] == installer.VERSION
    first_runtime = json.loads((target / "runtime.json").read_text())["python"]
    private = target / "my-paper.txt"
    private.write_text("User research")
    user_folder = target / "user-empty-directory"
    user_folder.mkdir()
    installer.install(target, wheel=wheel, update=True)
    second_runtime = json.loads((target / "runtime.json").read_text())["python"]
    assert first_runtime != second_runtime
    result = installer.uninstall(target)
    assert private.read_text() == "User research"
    assert user_folder.is_dir()
    assert "my-paper.txt" in result["preserved"]
    assert not (target / "SKILL.md").exists()
    assert not (target / "runtimes").exists()


def test_unmanaged_or_modified_installation_is_not_overwritten(installation):
    target, wheel = installation
    target.mkdir()
    (target / "private").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        installer.install(target, wheel=wheel)
    (target / "private").unlink()
    target.rmdir()
    installer.install(target, wheel=wheel)
    (target / "SKILL.md").write_text("user modifications")
    with pytest.raises(ValueError, match="modified"):
        installer.install(target, wheel=wheel, update=True)
    with pytest.raises(ValueError, match="modified"):
        installer.uninstall(target)
    assert (target / "SKILL.md").read_text() == "user modifications"


def test_failed_update_retains_previous_runtime(installation, monkeypatch):
    target, wheel = installation
    installer.install(target, wheel=wheel)
    previous = (target / "runtime.json").read_bytes()

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(installer.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(target, wheel=wheel, update=True)
    assert (target / "runtime.json").read_bytes() == previous
    installer.check_unchanged(target, installer.read_manifest(target))


def test_failed_fresh_install_can_be_retried(installation, monkeypatch):
    target, wheel = installation
    original = installer.subprocess.run

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(installer.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(target, wheel=wheel)
    assert not target.exists()
    monkeypatch.setattr(installer.subprocess, "run", original)
    assert installer.install(target, wheel=wheel)["status"] == "success"
