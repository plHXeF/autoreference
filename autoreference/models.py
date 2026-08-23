from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CitationAssessment(BaseModel):
    can_cite: bool = False
    relevance_score: int = Field(default=0, ge=0, le=100)
    reason: str = "Not assessed"
    supporting_points: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    assessed_by: str = "heuristic"


class ReferenceCandidate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str
    source_id: str | None = None
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    url: str | None = None
    publication_type: str | None = None
    bibtex: str | None = None
    assessment: CitationAssessment | None = None

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if not value:
            return None
        doi = value.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi.lower().startswith(prefix):
                doi = doi[len(prefix) :]
                break
        return doi.lower() or None


class SearchQueries(BaseModel):
    chinese: list[str] = Field(default_factory=list)
    english: list[str] = Field(default_factory=list)

    def all(self, fallback: str) -> list[str]:
        values = [*self.chinese, *self.english]
        deduped = list(dict.fromkeys(q.strip() for q in values if q.strip()))
        return deduped or [fallback]


class SearchRequest(BaseModel):
    claim: str = Field(min_length=3, max_length=8_000)
    sources: list[str] = Field(default_factory=lambda: ["openalex", "crossref"])
    max_results_per_source: int = Field(default=8, ge=1, le=25)
    use_llm: bool = True

    @field_validator("sources")
    @classmethod
    def normalize_sources(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if not normalized:
            raise ValueError("at least one source is required")
        return normalized


class SearchResult(BaseModel):
    claim: str
    queries: SearchQueries
    candidates: list[ReferenceCandidate]
    warnings: list[str] = Field(default_factory=list)
    llm_used: bool = False


class ExportRequest(BaseModel):
    candidates: list[ReferenceCandidate]

