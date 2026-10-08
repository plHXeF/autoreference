"""Conservative record matching with explicit provenance and conflicts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from difflib import SequenceMatcher

from autoreference.models import ReferenceCandidate


def normalized_title(title: str) -> str:
    return re.sub(r"[^\w]", "", title.casefold())


def same_record(left: ReferenceCandidate, right: ReferenceCandidate) -> str | None:
    if left.doi and right.doi:
        return "doi" if left.doi == right.doi else None
    a, b = normalized_title(left.title), normalized_title(right.title)
    if not a or not b:
        return None
    if left.year and right.year and left.year != right.year:
        return None
    if a == b:
        return "title-exact"
    if not (left.year and right.year and left.authors and right.authors):
        return None
    authors_a = {normalized_title(a) for a in left.authors}
    authors_b = {normalized_title(a) for a in right.authors}
    if authors_a & authors_b and SequenceMatcher(None, a, b).ratio() >= 0.95:
        return "title-year-author"
    return None


def merge_candidate(
    left: ReferenceCandidate, right: ReferenceCandidate, method: str
) -> ReferenceCandidate:
    data = left.model_dump()
    data["sources"] = list(dict.fromkeys([*left.sources, *right.sources]))
    data["source"] = "+".join(data["sources"])
    data["source_records"] = [*left.source_records]
    for record in right.source_records:
        if record not in data["source_records"]:
            data["source_records"].append(record)
    data["match_method"] = method
    data["conflicts"] = [*left.conflicts, *right.conflicts]
    data["metadata_changes"] = [*left.metadata_changes, *right.metadata_changes]
    for field in (
        "title",
        "abstract",
        "authors",
        "year",
        "journal",
        "doi",
        "url",
        "publication_type",
        "bibtex",
        "volume",
        "issue",
        "pages",
    ):
        value = getattr(right, field)
        if not data.get(field) and value:
            data[field] = value
        elif (
            field in {"title", "authors", "year", "journal", "volume", "issue", "pages"}
            and data.get(field)
            and value
            and data[field] != value
        ):
            conflict = {"field": field, "left": data[field], "right": value}
            if conflict not in data["conflicts"]:
                data["conflicts"].append(conflict)
    data["citations"] = max(left.citations, right.citations)
    if right.metadata_status == "verified":
        data["metadata_status"] = right.metadata_status
        data["verification"] = right.verification
    return ReferenceCandidate.model_validate(data)


def deduplicate(candidates: Iterable[ReferenceCandidate]) -> list[ReferenceCandidate]:
    unique: list[ReferenceCandidate] = []
    for candidate in candidates:
        for index, current in enumerate(unique):
            method = same_record(current, candidate)
            if method:
                unique[index] = merge_candidate(current, candidate, method)
                break
        else:
            unique.append(candidate)
    return unique
