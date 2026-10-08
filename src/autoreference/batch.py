from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from autoreference.exporters import citation_key, export_bibtex
from autoreference.models import ReferenceCandidate, SearchRequest
from autoreference.service import SearchService
from autoreference.text import split_sentences

ProgressCallback = Callable[[int, int, str], None]


async def analyze_paper(
    paper_path: Path,
    output_dir: Path,
    service: SearchService,
    *,
    sources: list[str],
    max_results_per_source: int = 6,
    use_llm: bool = True,
    minimum_score: int = 70,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    text = paper_path.read_text(encoding="utf-8")
    sentences = split_sentences(text)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    selected_by_key: dict[str, ReferenceCandidate] = {}

    for index, sentence in enumerate(sentences, start=1):
        if progress:
            progress(index, len(sentences), sentence)
        result = await service.search(
            SearchRequest(
                claim=sentence,
                sources=sources,
                max_results_per_source=max_results_per_source,
                use_llm=use_llm,
            )
        )
        recommended = [
            candidate
            for candidate in result.candidates
            if candidate.assessment
            and candidate.assessment.can_cite
            and candidate.assessment.relevance_score >= minimum_score
        ]
        for candidate in recommended:
            selected_by_key.setdefault(citation_key(candidate), candidate)
        entries.append(
            {
                "sentence_index": index,
                "sentence": sentence,
                "queries": result.queries.model_dump(mode="json"),
                "warnings": result.warnings,
                "recommended_keys": [citation_key(candidate) for candidate in recommended],
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in result.candidates
                ],
            }
        )

    report = {
        "status": "candidate-search; human verification required",
        "paper": str(paper_path),
        "sentence_count": len(sentences),
        "recommended_reference_count": len(selected_by_key),
        "entries": entries,
    }
    (output_dir / "citation_candidates.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "references.bib").write_text(
        export_bibtex(list(selected_by_key.values())), encoding="utf-8"
    )
    return report
