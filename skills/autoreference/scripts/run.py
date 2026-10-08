#!/usr/bin/env python3
"""Delegate to the pinned installation; never install anything during invocation."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    try:
        config = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
        python = root / config["python"]
        if not python.is_file():
            raise ValueError("The installed Python runtime is unavailable.")
        return subprocess.call([str(python), "-m", "autoreference.cli", *sys.argv[1:]])
    except (OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "failed",
                    "error": {"code": "installation_required", "message": str(exc)},
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
