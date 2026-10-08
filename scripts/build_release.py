#!/usr/bin/env python3
"""Build a redistributable skill + installer + pinned wheel, without private materials."""

import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.2.0a0"


def main():
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "--wheel-dir", str(dist)],
        check=True,
    )
    bundle = dist / f"autoreference-skill-{VERSION}"
    if bundle.exists():
        shutil.rmtree(bundle)
    (bundle / "scripts").mkdir(parents=True)
    shutil.copytree(
        root / "skills" / "autoreference",
        bundle / "skills" / "autoreference",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(root / "scripts" / "install_skill.py", bundle / "scripts" / "install_skill.py")
    wheel = next(dist.glob(f"autoreference-{VERSION}-*.whl"))
    shutil.copyfile(wheel, bundle / wheel.name)
    shutil.copyfile(root / "README.md", bundle / "README.md")
    archive = shutil.make_archive(str(bundle), "zip", root_dir=bundle.parent, base_dir=bundle.name)
    print(archive)


if __name__ == "__main__":
    main()
