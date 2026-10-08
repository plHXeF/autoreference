#!/usr/bin/env python3
"""Build a redistributable skill + installer + pinned wheel, without private materials."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.2.0a0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build-isolation", action="store_true",
        help="Use an already installed build backend instead of downloading it.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "--wheel-dir", str(dist),
         *(["--no-build-isolation"] if args.no_build_isolation else [])],
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
    shutil.copyfile(root / ".env.example", bundle / ".env.example")
    if (root / "docs").is_dir():
        shutil.copytree(root / "docs", bundle / "docs")
    archive = shutil.make_archive(str(bundle), "zip", root_dir=bundle.parent, base_dir=bundle.name)
    print(archive)


if __name__ == "__main__":
    main()
