"""Resolve bibliographic metadata against Crossref; never infer claim support."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from autoreference.matching import merge_candidate, normalized_title
from autoreference.models import ReferenceCandidate
from autoreference.providers.crossref import _first, _plain_abstract, _year
from autoreference.providers.http import request_json


def crossref_candidate(record: dict) -> ReferenceCandidate:
    return ReferenceCandidate(
        source="crossref",
        source_id=record.get("DOI"),
        doi=record.get("DOI"),
        title=_first(record.get("title")),
        authors=[
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in record.get("author", [])
        ],
        year=_year(record),
        journal=_first(record.get("container-title")) or None,
        abstract=_plain_abstract(record.get("abstract")),
        url=record.get("URL"),
        publication_type=record.get("type"),
        volume=record.get("volume"),
        issue=record.get("issue"),
        pages=record.get("page"),
    )


async def resolve_reference(
    client: httpx.AsyncClient,
    *,
    candidate: ReferenceCandidate | None = None,
    raw: str | None = None,
    doi_hint: str | None = None,
) -> ReferenceCandidate | None:
    doi = candidate.doi if candidate else doi_hint
    base = "https://api.crossref.org/works"
    if doi:
        data = await request_json(client, "GET", base + "/" + quote(doi, safe=""))
        records = [data.get("message", {})]
    else:
        data = await request_json(
            client,
            "GET",
            base,
            params={"query.bibliographic": candidate.title if candidate else raw, "rows": 5},
        )
        records = data.get("message", {}).get("items", [])
    for record in records:
        found = crossref_candidate(record)
        if not found.title or not found.doi:
            continue
        if doi and found.doi != ReferenceCandidate(source="input", title="", doi=doi).doi:
            continue
        if candidate:
            title_matches = normalized_title(candidate.title) == normalized_title(found.title)
            authors_match = bool(
                set(map(normalized_title, candidate.authors))
                & set(map(normalized_title, found.authors))
            )
            year_matches = not candidate.year or candidate.year == found.year
            if not title_matches or not year_matches or (candidate.authors and not authors_match):
                if doi:
                    candidate.metadata_status = "conflict"
                    candidate.verification = {
                        "status": "conflict",
                        "url": found.url,
                        "authoritative_record": found.model_dump(mode="json"),
                    }
                    return candidate
                continue
            if not doi and not (candidate.year and candidate.authors and authors_match):
                continue
            merged = merge_candidate(candidate, found, "doi" if doi else "title-year-author")
        else:
            # Raw entries with no DOI have no reliable title/author boundaries yet.
            if not doi:
                continue
            merged = found
        merged.metadata_status = "verified"
        for field in (
            "title",
            "authors",
            "year",
            "journal",
            "doi",
            "url",
            "publication_type",
            "volume",
            "issue",
            "pages",
        ):
            value = getattr(found, field)
            before = getattr(candidate, field) if candidate else None
            if value and before != value:
                merged.metadata_changes.append(
                    {"field": field, "before": before, "after": value, "source": "crossref"}
                )
                setattr(merged, field, value)
        for difference in merged.conflicts:
            difference["resolution"] = "authoritative-metadata"
            difference["resolved_value"] = getattr(merged, difference["field"], None)
        merged.verification = {
            "status": "verified",
            "method": "doi" if doi else "title-year-author",
            "url": base + "/" + quote(found.doi, safe=""),
            "authoritative_record": found.model_dump(mode="json"),
            "normalization_revision": 1,
        }
        return merged
    if candidate:
        candidate.verification = {"status": "unverified", "reason": "No unambiguous metadata match"}
    return candidate
