from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from autoreference.matching import deduplicate
from autoreference.models import (
    CitationAssessment,
    ReferenceCandidate,
    SearchQueries,
    SearchRequest,
    SearchResult,
)
from autoreference.providers.base import SearchProvider
from autoreference.text import search_tokens

if TYPE_CHECKING:
    from autoreference.llm import LLMClient


def heuristic_assessment(claim: str, candidate: ReferenceCandidate) -> CitationAssessment:
    claim_tokens = search_tokens(claim)
    candidate_tokens = search_tokens(f"{candidate.title} {candidate.abstract}")
    overlap = len(claim_tokens & candidate_tokens)
    denominator = max(1, min(len(claim_tokens), 18))
    score = min(60, round(overlap / denominator * 100))
    caveats = ["LLM assessment was not used; verify the abstract and full text manually."]
    if not candidate.abstract:
        caveats.append("No abstract was returned by the source.")
        score = min(score, 35)
    return CitationAssessment(
        can_cite=False,
        relevance_score=score,
        reason=(
            "Keyword-overlap fallback score; this is not evidence that the paper supports "
            "the claim."
        ),
        caveats=caveats,
        assessed_by="local-heuristic",
    )


class SearchService:
    def __init__(
        self,
        providers: dict[str, SearchProvider],
        llm: LLMClient | None = None,
        *,
        max_candidates_for_judging: int = 20,
        provider_factories: dict[str, Callable[[], SearchProvider]] | None = None,
    ) -> None:
        self.providers = providers
        self.provider_factories = provider_factories or {}
        self.llm = llm
        self.max_candidates_for_judging = max_candidates_for_judging

    @property
    def available_providers(self) -> list[str]:
        return list(dict.fromkeys([*self.providers, *self.provider_factories]))

    def _get_provider(self, source: str) -> SearchProvider | None:
        provider = self.providers.get(source)
        if provider is None and source in self.provider_factories:
            provider = self.provider_factories[source]()
            self.providers[source] = provider
        return provider

    async def search(self, request: SearchRequest) -> SearchResult:
        warnings: list[str] = []
        queries = SearchQueries(english=[request.claim])
        llm_used = bool(request.use_llm and self.llm)

        if request.use_llm and self.llm:
            try:
                queries = await self.llm.generate_queries(request.claim)
            except Exception as exc:  # one failed enhancement must not block search
                llm_used = False
                warnings.append(
                    f"Query expansion failed; searched the original claim instead: {exc}"
                )
        elif request.use_llm:
            warnings.append("OPENAI_API_KEY is not set; using local fallback ranking.")

        selected_providers = []
        for source in request.sources:
            provider = self._get_provider(source)
            if provider:
                selected_providers.append(provider)
            else:
                warnings.append(f"Unknown or unavailable source: {source}")
        if not selected_providers:
            return SearchResult(
                claim=request.claim,
                queries=queries,
                candidates=[],
                warnings=warnings,
                llm_used=False,
            )

        tasks = [
            provider.search(query, request.max_results_per_source)
            for provider in selected_providers
            for query in queries.all(request.claim)
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        candidates: list[ReferenceCandidate] = []
        for result in raw_results:
            if isinstance(result, BaseException):
                warnings.append(str(result))
            else:
                candidates.extend(result)

        candidates = deduplicate(candidates)
        for candidate in candidates:
            candidate.assessment = heuristic_assessment(request.claim, candidate)
        candidates.sort(
            key=lambda candidate: (
                candidate.assessment.relevance_score if candidate.assessment else 0
            ),
            reverse=True,
        )
        candidates = candidates[: self.max_candidates_for_judging]

        if request.use_llm and self.llm and candidates:
            try:
                assessments = await self.llm.assess_candidates(request.claim, candidates)
                for candidate, assessment in zip(candidates, assessments, strict=True):
                    candidate.assessment = assessment
                candidates.sort(
                    key=lambda candidate: (
                        candidate.assessment.relevance_score if candidate.assessment else 0
                    ),
                    reverse=True,
                )
                llm_used = True
            except Exception as exc:
                llm_used = False
                warnings.append(f"LLM assessment failed; showing local fallback scores: {exc}")

        return SearchResult(
            claim=request.claim,
            queries=queries,
            candidates=candidates,
            warnings=warnings,
            llm_used=llm_used,
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(provider.close() for provider in self.providers.values()),
            return_exceptions=True,
        )
        if self.llm:
            await self.llm.close()
