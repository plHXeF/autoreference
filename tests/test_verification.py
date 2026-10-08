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
