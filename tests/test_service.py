from autoreference.models import (
    CitationAssessment,
    ReferenceCandidate,
    SearchQueries,
    SearchRequest,
)
from autoreference.service import SearchService


class FakeProvider:
    name = "fake"

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        assert limit == 5
        return [
            ReferenceCandidate(
                source=self.name,
                title="Swin Transformer for geological image analysis",
                abstract="Shifted windows model local and cross-window context.",
                doi="10.1/swin",
                year=2021,
            )
        ]

    async def close(self) -> None:
        return None


class FakeLLM:
    async def generate_queries(self, claim: str) -> SearchQueries:
        return SearchQueries(english=["Swin Transformer geology"])

    async def assess_candidates(
        self, claim: str, candidates: list[ReferenceCandidate]
    ) -> list[CitationAssessment]:
        return [
            CitationAssessment(
                can_cite=True,
                relevance_score=91,
                reason="The supplied abstract directly addresses the mechanism.",
                assessed_by="fake",
            )
            for _ in candidates
        ]

    async def close(self) -> None:
        return None


async def test_lazy_provider_is_only_created_when_selected() -> None:
    created = 0

    def create_provider() -> FakeProvider:
        nonlocal created
        created += 1
        return FakeProvider()

    service = SearchService({}, provider_factories={"fake": create_provider})

    assert service.available_providers == ["fake"]
    unavailable = await service.search(
        SearchRequest(
            claim="A claim with no matching provider",
            sources=["other"],
            max_results_per_source=5,
            use_llm=False,
        )
    )
    assert created == 0
    assert unavailable.warnings == ["Unknown or unavailable source: other"]

    await service.search(
        SearchRequest(
            claim="Swin Transformer for geological image analysis.",
            sources=["fake"],
            max_results_per_source=5,
            use_llm=False,
        )
    )
    await service.search(
        SearchRequest(
            claim="Swin Transformer for geological image analysis.",
            sources=["fake"],
            max_results_per_source=5,
            use_llm=False,
        )
    )
    assert created == 1


async def test_service_uses_batch_assessment_and_deduplicates() -> None:
    service = SearchService({"fake": FakeProvider()}, FakeLLM())
    result = await service.search(
        SearchRequest(
            claim="Swin Transformer uses shifted windows to model context.",
            sources=["fake"],
            max_results_per_source=5,
        )
    )
    assert result.llm_used is True
    assert len(result.candidates) == 1
    assert result.candidates[0].assessment.relevance_score == 91


async def test_service_degrades_without_llm() -> None:
    service = SearchService({"fake": FakeProvider()})
    result = await service.search(
        SearchRequest(
            claim="Swin Transformer for geological image analysis.",
            sources=["fake"],
            max_results_per_source=5,
            use_llm=True,
        )
    )
    assert result.llm_used is False
    assert result.warnings
    assert result.candidates[0].assessment.assessed_by == "local-heuristic"
    assert result.candidates[0].assessment.can_cite is False
