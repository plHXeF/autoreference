import httpx

from autoreference.providers.crossref import CrossrefProvider
from autoreference.providers.openalex import OpenAlexProvider


async def test_openalex_maps_api_record() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == "core image"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Core image analysis",
                        "publication_year": 2023,
                        "doi": "https://doi.org/10.1/example",
                        "abstract_inverted_index": {"Useful": [0], "evidence": [1]},
                        "authorships": [{"author": {"display_name": "Ada Stone"}}],
                        "primary_location": {
                            "landing_page_url": "https://example.test/paper",
                            "source": {"display_name": "Geology"},
                        },
                        "type": "article",
                    }
                ]
            },
        )

    provider = OpenAlexProvider(headers={}, transport=httpx.MockTransport(handler))
    try:
        results = await provider.search("core image", 5)
    finally:
        await provider.close()
    assert results[0].title == "Core image analysis"
    assert results[0].abstract == "Useful evidence"
    assert results[0].doi == "10.1/example"


async def test_crossref_maps_api_record_and_strips_markup() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "DOI": "10.2/example",
                            "URL": "https://doi.org/10.2/example",
                            "title": ["A useful paper"],
                            "abstract": "<jats:p>Some evidence.</jats:p>",
                            "author": [{"given": "Lin", "family": "Chen"}],
                            "container-title": ["Journal"],
                            "published-online": {"date-parts": [[2022, 5, 1]]},
                            "type": "journal-article",
                        }
                    ]
                }
            },
        )

    provider = CrossrefProvider(headers={}, transport=httpx.MockTransport(handler))
    try:
        results = await provider.search("useful", 5)
    finally:
        await provider.close()
    assert results[0].abstract == "Some evidence."
    assert results[0].authors == ["Lin Chen"]
    assert results[0].year == 2022

