"""Compatibility entry point. Prefer the installed ``autoreference`` command."""

from autoreference.cli import app

if __name__ == "__main__":
    app()
