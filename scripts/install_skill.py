#!/usr/bin/env python3
"""Install/update a pinned AutoReference runtime alongside a portable agent skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import venv
from contextlib import contextmanager, suppress
from pathlib import Path

VERSION = "0.2.0a0"
OWNER = "autoreference-skill-installer-v1"
MANIFEST = ".autoreference-install.json"


def digest(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def write_json(file: Path, value: dict) -> None:
    temporary = file.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(file)


def managed_path(target: Path, name: str) -> Path:
    path = target / name
    if path.is_symlink() or not path.resolve().is_relative_to(target.resolve()):
        raise ValueError("Managed paths must remain inside the installation directory.")
    return path


def read_manifest(target: Path) -> dict:
    file = target / MANIFEST
    if target.is_symlink() or file.is_symlink():
        raise ValueError("Linked installation directories are not supported.")
    data = json.loads(file.read_text(encoding="utf-8"))
    if data.get("owner") != OWNER:
        raise ValueError("This directory is not owned by the AutoReference installer.")
    return data


def check_unchanged(target: Path, manifest: dict) -> None:
    for name, expected in manifest["files"].items():
        path = managed_path(target, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Locally modified managed file: {name}; preserve it before updating.")


@contextmanager
def installation_lock(target: Path):
    target = target.expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / (".autoreference-install-" + target.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("Installation is locked by another process.") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def uninstall(target: Path) -> dict:
    with installation_lock(target):
        return _uninstall(target.expanduser().absolute())


def _uninstall(target: Path) -> dict:
    manifest = read_manifest(target)
    check_unchanged(target, manifest)
    runtimes = [managed_path(target, name) for name in manifest["runtimes"]]
    for runtime in runtimes:
        if runtime.exists() and not (runtime / ".autoreference-runtime").is_file():
            raise ValueError("Refusing to remove an unmanaged runtime.")
    folders = set()
    for name in manifest["files"]:
        file = managed_path(target, name)
        folders.update(p for p in file.parents if p != target and p.is_relative_to(target))
        file.unlink()
    for runtime in runtimes:
        folders.add(runtime.parent)
        if runtime.exists():
            shutil.rmtree(runtime)
    (target / MANIFEST).unlink()
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        with suppress(OSError):
            folder.rmdir()
    remaining = [str(p.relative_to(target)) for p in target.iterdir()]
    if not remaining:
        target.rmdir()
    return {"status": "success", "uninstalled": str(target), "preserved": remaining}


def install(target: Path, **kwargs) -> dict:
    with installation_lock(target):
        return _install(target, **kwargs)


def _install(
    target: Path,
    *,
    update: bool = False,
    with_campus: bool = False,
    wheel: Path | None = None,
    wheelhouse: Path | None = None,
) -> dict:
    if sys.version_info < (3, 11):  # noqa: UP036 - installer may be invoked before package checks
        raise ValueError("Python 3.11 or newer is required.")
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError("Linked installation directories are not supported.")
    old = None
    if target.exists():
        if not update or not (target / MANIFEST).is_file():
            raise ValueError("Target already exists; use --update only for an owned installation.")
        old = read_manifest(target)
        check_unchanged(target, old)
        with_campus = with_campus or old.get("campus", False)
    elif update:
        raise ValueError("Nothing installed at the specified directory.")
    source_root = Path(__file__).resolve().parent.parent
    skill = source_root / "skills" / "autoreference"
    if not (skill / "SKILL.md").is_file():
        raise ValueError("Skill resources are missing from this distribution.")
    sources = [
        s
        for s in skill.rglob("*")
        if s.is_file() and s.suffix != ".pyc" and "__pycache__" not in s.parts
    ]
    for source in sources:
        name = source.relative_to(skill).as_posix()
        file = managed_path(target, name)
        if file.exists() and (old is None or name not in old["files"]):
            raise ValueError(f"Refusing to overwrite an unmanaged file: {name}")
    if wheel is None:
        wheels = sorted((source_root / "dist").glob(f"autoreference-{VERSION}-*.whl"))
        wheels += sorted(source_root.glob(f"autoreference-{VERSION}-*.whl"))
        wheel = wheels[0] if wheels else None
    if wheel is not None and not wheel.name.startswith(f"autoreference-{VERSION}-"):
        raise ValueError(f"Expected an AutoReference {VERSION} wheel.")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime_name = "runtimes/" + uuid.uuid4().hex
    runtime = managed_path(target, runtime_name)
    runtime.parent.mkdir(exist_ok=True)
    created_files = []
    previous = (
        {name: managed_path(target, name).read_bytes() for name in old["files"]} if old else {}
    )
    manifest_before = (target / MANIFEST).read_bytes() if old else None
    try:
        venv.EnvBuilder(with_pip=True).create(runtime)
        (runtime / ".autoreference-runtime").write_text(OWNER)
        executable = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if wheel is None:
            if not (source_root / "pyproject.toml").is_file():
                raise ValueError("A pinned wheel is required in a release distribution.")
            build = runtime / "wheel"
            subprocess.run(
                [
                    str(executable),
                    "-m",
                    "pip",
                    "wheel",
                    str(source_root),
                    "--no-deps",
                    "--wheel-dir",
                    str(build),
                ],
                check=True,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
            wheel = next(build.glob(f"autoreference-{VERSION}-*.whl"))
        requirement = str(wheel.resolve()) + ("[zhizhen]" if with_campus else "")
        command = [str(executable), "-m", "pip", "install", requirement]
        if wheelhouse:
            command += ["--no-index", "--find-links", str(wheelhouse.resolve())]
        subprocess.run(command, check=True, stdout=sys.stderr, stderr=sys.stderr)
        version = subprocess.check_output(
            [
                str(executable),
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('autoreference'))",
            ],
            text=True,
        ).strip()
        if version != VERSION:
            raise ValueError("Installed runtime does not match the pinned skill version.")
        subprocess.run(
            [str(executable), "-m", "autoreference.cli", "doctor"],
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        files = dict(old["files"]) if old else {}
        for source in sources:
            relative = source.relative_to(skill).as_posix()
            destination = managed_path(target, relative)
            if destination.exists() and (old is None or relative not in old["files"]):
                raise ValueError(f"Refusing to overwrite an unmanaged file: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            created_files.append(relative)
            shutil.copyfile(source, destination)
            files[relative] = digest(destination)
        config = {"version": VERSION, "python": executable.relative_to(target).as_posix()}
        write_json(target / "runtime.json", config)
        files["runtime.json"] = digest(target / "runtime.json")
        runtimes = [*(old["runtimes"] if old else []), runtime_name]
        write_json(
            target / MANIFEST,
            {
                "owner": OWNER,
                "version": VERSION,
                "files": files,
                "runtimes": runtimes,
                "campus": with_campus,
            },
        )
        return {
            "status": "success",
            "version": VERSION,
            "skill_dir": str(target),
            "launcher": str(target / "scripts" / "run.py"),
            "campus": with_campus,
        }
    except Exception:
        if runtime.exists():
            shutil.rmtree(runtime)
        for name in [*created_files, "runtime.json"]:
            file = managed_path(target, name)
            if name in previous:
                file.write_bytes(previous[name])
            else:
                file.unlink(missing_ok=True)
        if manifest_before is not None:
            (target / MANIFEST).write_bytes(manifest_before)
        if old is None:
            folders = {runtime.parent}
            for name in created_files:
                folders.update(
                    p for p in (target / name).parents if p != target and p.is_relative_to(target)
                )
            for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
                with suppress(OSError):
                    folder.rmdir()
            with suppress(OSError):
                target.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--with-campus", action="store_true")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    options = parser.parse_args()
    if options.update and options.uninstall:
        parser.error("--update and --uninstall are mutually exclusive")
    try:
        result = (
            uninstall(options.skill_dir.expanduser().absolute())
            if options.uninstall
            else install(
                options.skill_dir,
                update=options.update,
                with_campus=options.with_campus,
                wheel=options.wheel,
                wheelhouse=options.wheelhouse,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
