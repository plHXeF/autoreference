from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from autoreference.agent_cli import access_app, doctor, task_app
from autoreference.batch import analyze_paper
from autoreference.config import Settings
from autoreference.exporters import export_bibtex
from autoreference.factory import create_service
from autoreference.models import SearchRequest

app = typer.Typer(
    no_args_is_help=True,
    help="Find, assess, and export possible scholarly citations.",
)

app.add_typer(task_app, name="task")
app.add_typer(access_app, name="access")
app.command()(doctor)


def _settings() -> Settings:
    load_dotenv()
    return Settings.from_env()


def _source_list(value: str) -> list[str]:
    return list(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))


@app.command()
def search(
    claim: Annotated[str, typer.Argument(help="Claim or sentence that needs citations")],
    sources: Annotated[str, typer.Option(help="Comma-separated providers")] = "openalex,crossref",
    limit: Annotated[int, typer.Option(min=1, max=25)] = 8,
    no_llm: Annotated[
        bool, typer.Option(help="Disable LLM query expansion and assessment")
    ] = False,
    bibtex: Annotated[
        Path | None, typer.Option(help="Write displayed candidates to this BibTeX file")
    ] = None,
) -> None:
    """Search for possible citations for one claim."""

    async def run() -> None:
        selected_sources = _source_list(sources)
        service = create_service(
            _settings(), include_zhizhen="zhizhen" in selected_sources, enable_llm=not no_llm
        )
        try:
            result = await service.search(
                SearchRequest(
                    claim=claim,
                    sources=selected_sources,
                    max_results_per_source=limit,
                    use_llm=not no_llm,
                )
            )
            typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
            if bibtex:
                bibtex.write_text(export_bibtex(result.candidates), encoding="utf-8")
                typer.echo(f"BibTeX written to {bibtex}", err=True)
        finally:
            await service.close()

    asyncio.run(run())


@app.command("paper")
def paper_command(
    paper: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output_dir: Annotated[Path, typer.Option("--output", "-o")] = Path("output"),
    sources: Annotated[str, typer.Option(help="Comma-separated providers")] = "openalex,crossref",
    limit: Annotated[int, typer.Option(min=1, max=25)] = 6,
    minimum_score: Annotated[int, typer.Option(min=0, max=100)] = 70,
    no_llm: Annotated[
        bool, typer.Option(help="Disable LLM query expansion and assessment")
    ] = False,
) -> None:
    """Analyze every sentence and save a candidate report plus conservative BibTeX export."""

    def progress(index: int, total: int, sentence: str) -> None:
        typer.echo(f"[{index}/{total}] {sentence[:60]}", err=True)

    async def run() -> None:
        selected_sources = _source_list(sources)
        service = create_service(
            _settings(), include_zhizhen="zhizhen" in selected_sources, enable_llm=not no_llm
        )
        try:
            report = await analyze_paper(
                paper,
                output_dir,
                service,
                sources=selected_sources,
                max_results_per_source=limit,
                use_llm=not no_llm,
                minimum_score=minimum_score,
                progress=progress,
            )
            typer.echo(
                f"Done: {report['sentence_count']} sentences, "
                f"{report['recommended_reference_count']} recommended references."
            )
            typer.echo(f"Review the report in {output_dir.resolve()}")
        finally:
            await service.close()

    asyncio.run(run())


@app.command()
def web(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Development auto-reload")] = False,
) -> None:
    """Start the local Web UI."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("Install autoreference[web] to start the Web UI.", err=True)
        raise typer.Exit(1) from None

    uvicorn.run("autoreference.web:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
