"""Compatibility helpers for the 2025 prototype API.

New integrations should import from :mod:`autoreference` instead.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from autoreference.batch import analyze_paper
from autoreference.config import Settings
from autoreference.factory import create_service


def process_paper(paper_path: str, bib_path: str, csv_path: str) -> bool:
    """Run the modern pipeline while accepting the old function signature.

    ``bib_path`` is honored. The obsolete sentence-prefix CSV is replaced by the
    richer ``citation_candidates.json`` report in the same directory.
    """

    del csv_path
    load_dotenv()
    settings = Settings.from_env()
    output_dir = Path(bib_path).resolve().parent

    async def run() -> bool:
        service = create_service(settings)
        try:
            await analyze_paper(
                Path(paper_path),
                output_dir,
                service,
                sources=["openalex", "crossref"],
                use_llm=settings.llm_enabled,
            )
            generated = output_dir / "references.bib"
            requested = Path(bib_path).resolve()
            if generated != requested:
                requested.write_text(generated.read_text(encoding="utf-8"), encoding="utf-8")
            return True
        finally:
            await service.close()

    return asyncio.run(run())

