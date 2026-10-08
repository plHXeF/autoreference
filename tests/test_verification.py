import httpx

from autoreference.models import ReferenceCandidate
from autoreference.verification import resolve_reference


async def test_doi_conflict_does_not_become_verified():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"message": {"DOI": "10.1234/a", "title": ["Completely different paper"]}}
            )
        )
    )
    candidate = ReferenceCandidate(source="test", title="The claimed paper", doi="10.1234/a")
    try:
        result = await resolve_reference(client, candidate=candidate)
    finally:
        await client.aclose()
    assert result.metadata_status == "conflict"


async def test_title_only_is_not_enough_for_verification():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={"message": {"items": [{"DOI": "10.1234/a", "title": ["The claimed paper"]}]}},
            )
        )
    )
    try:
        result = await resolve_reference(
            client, candidate=ReferenceCandidate(source="test", title="The claimed paper")
        )
    finally:
        await client.aclose()
    assert result.metadata_status == "unverified"


async def test_historical_format_differences_are_resolved_and_changes_recorded():
    original = ReferenceCandidate(
        source="openalex",
        title="The paper",
        year=2021,
        doi="10.1234/a",
        authors=["Ming‐Wei Chang"],
        journal="Short venue",
        conflicts=[{"field": "journal", "left": "Short venue", "right": "Full venue"}],
    )
    record = {
        "DOI": "10.1234/a",
        "title": ["The paper"],
        "author": [{"given": "Ming-Wei", "family": "Chang"}],
        "issued": {"date-parts": [[2021]]},
        "container-title": ["Full venue"],
        "page": "1-9",
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"message": record}))
    ) as client:
        result = await resolve_reference(client, candidate=original)
    assert result.metadata_status == "verified"
    assert result.journal == "Full venue"
    assert result.pages == "1-9"
    assert result.conflicts[0]["resolution"] == "authoritative-metadata"
    assert any(c["field"] == "pages" and c["before"] is None for c in result.metadata_changes)
