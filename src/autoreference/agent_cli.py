"""Versioned JSON commands; model and web extras are intentionally not imported."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from autoreference import __version__
from autoreference.config import Settings
from autoreference.workflow import (
    SCHEMA_VERSION,
    finalize,
    load_task,
    prepare,
    search_task,
    verify_task,
)

task_app = typer.Typer(help="Model-free document/citation tasks with JSON output.")
access_app = typer.Typer(help="Dedicated sessions for user-operated campus login.")


def emit(operation: str, callback) -> None:
    try:
        data = callback()
        status = (
            data.get("protocol_status", data.get("status", "success"))
            if isinstance(data, dict)
            else "success"
        )
        if status not in {"success", "partial", "failed", "needs_user_action"}:
            status = "success"
        result = {
            "schema_version": SCHEMA_VERSION,
            "operation": operation,
            "status": status,
            "data": data,
        }
    except Exception as exc:
        # Do not serialize HTTP exceptions; URLs can contain credentials.
        message = (
            str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else type(exc).__name__
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "operation": operation,
            "status": "failed",
            "error": {"code": getattr(exc, "code", "invalid_input"), "message": message},
        }
        typer.echo(json.dumps(result, ensure_ascii=False))
        raise typer.Exit(1) from None
    typer.echo(json.dumps(result, ensure_ascii=False))


def read_payload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@task_app.command("prepare")
def prepare_command(
    output: Annotated[Path, typer.Option("--output", "-o")],
    text: Annotated[str | None, typer.Option()] = None,
    input_file: Annotated[Path | None, typer.Option("--input")] = None,
) -> None:
    emit("task.prepare", lambda: prepare(output, text=text, path=input_file))


@task_app.command("search")
def search_command(
    directory: Path,
    requests: Annotated[Path, typer.Option("--requests")],
    refresh: Annotated[bool, typer.Option()] = False,
) -> None:
    emit(
        "task.search",
        lambda: asyncio.run(
            search_task(directory, read_payload(requests), Settings.from_env(), refresh=refresh)
        ),
    )


@task_app.command("verify")
def verify_command(
    directory: Path,
    evidence: Annotated[Path | None, typer.Option()] = None,
    references: Annotated[Path | None, typer.Option()] = None,
) -> None:
    emit(
        "task.verify",
        lambda: asyncio.run(
            verify_task(
                directory,
                Settings.from_env(),
                evidence=read_payload(evidence) if evidence else None,
                references=read_payload(references) if references else None,
            )
        ),
    )


@task_app.command("finalize")
def finalize_command(
    directory: Path,
    decisions: Annotated[Path, typer.Option("--decisions")],
) -> None:
    emit("task.finalize", lambda: finalize(directory, read_payload(decisions)))


@task_app.command("inspect")
def inspect_command(
    directory: Path, claim_id: Annotated[str | None, typer.Option()] = None
) -> None:
    def inspect():
        state = load_task(directory)
        if not claim_id:
            return state
        claims = [c for c in state["document"]["claims"] if c["id"] == claim_id]
        if not claims:
            raise ValueError("Unknown claim_id")
        keys = state["claim_candidates"].get(claim_id, [])
        return {
            "claims": claims,
            "candidates": {k: state["candidates"][k] for k in keys},
            "evidence": {k: v for k, v in state["evidence"].items() if v["candidate_id"] in keys},
        }

    emit("task.inspect", inspect)


@access_app.command("status")
def access_status() -> None:
    from autoreference.access import status

    emit("access.status", lambda: status(Settings.from_env()))


@access_app.command("login")
def access_login(timeout: Annotated[int, typer.Option(min=1, max=600)] = 180) -> None:
    from autoreference.access import login

    typer.echo(
        "Complete school login and any verification in the dedicated browser. "
        "Then navigate to a Zhizhen search result page. No credentials are read by this tool.",
        err=True,
    )

    def run():
        result = login(Settings.from_env(), timeout)
        return {
            "status": "success" if result["state"] == "ready" else "needs_user_action",
            **result,
        }

    emit("access.login", run)


@access_app.command("reset")
def access_reset() -> None:
    from autoreference.access import reset

    emit("access.reset", lambda: reset(Settings.from_env()))


def doctor() -> None:
    def inspect():
        settings = Settings.from_env()
        return {
            "version": __version__,
            "python": sys.version.split()[0],
            "extras": {
                name: importlib.util.find_spec(module) is not None
                for name, module in {
                    "web": "fastapi",
                    "llm": "openai",
                    "campus": "selenium",
                }.items()
            },
            "configured": {
                "anysearch": bool(settings.anysearch_api_key),
                "openalex_key": bool(settings.openalex_api_key),
                "model_api": settings.llm_enabled,
                "campus_login": bool(settings.campus_login_url),
            },
            "network_checked": False,
        }

    emit("doctor", inspect)
