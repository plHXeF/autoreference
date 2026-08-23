from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from autoreference.config import Settings
from autoreference.exporters import export_bibtex, export_csv, export_json
from autoreference.factory import create_service
from autoreference.models import ExportRequest, SearchRequest, SearchResult

STATIC_DIR = Path(__file__).with_name("static")

load_dotenv()
settings = Settings.from_env()
service = create_service(settings, include_zhizhen=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await service.close()


app = FastAPI(
    title="AutoReference",
    version="0.1.0a0",
    description="Candidate citation search. Human verification is required.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": app.version,
        "llm_enabled": settings.llm_enabled,
        "query_model": settings.query_model if settings.llm_enabled else None,
        "judge_model": settings.judge_model if settings.llm_enabled else None,
        "reasoning_effort": settings.reasoning_effort,
        "providers": list(service.providers),
        "unverified_providers": ["zhizhen"],
    }


@app.post("/api/search", response_model=SearchResult)
async def search(request: SearchRequest) -> SearchResult:
    try:
        return await service.search(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/export/{format_name}", response_class=PlainTextResponse)
async def export(format_name: str, request: ExportRequest) -> PlainTextResponse:
    if format_name == "bibtex":
        return PlainTextResponse(
            export_bibtex(request.candidates), media_type="application/x-bibtex"
        )
    if format_name == "csv":
        return PlainTextResponse(export_csv(request.candidates), media_type="text/csv")
    if format_name == "json":
        return PlainTextResponse(export_json(request.candidates), media_type="application/json")
    raise HTTPException(status_code=404, detail="Supported formats: bibtex, csv, json")
