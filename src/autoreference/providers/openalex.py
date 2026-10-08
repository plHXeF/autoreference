from __future__ import annotations

import httpx

from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError
from autoreference.providers.http import request_json


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positioned = sorted(
        (position, word) for word, positions in index.items() for position in positions
    )
    return " ".join(word for _, word in positioned)


class OpenAlexProvider:
    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        headers: dict[str, str],
        contact_email: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.contact_email = contact_email
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        params: dict[str, str | int] = {"search": query, "per-page": limit}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.contact_email:
            params["mailto"] = self.contact_email
        try:
            data = await request_json(self.client, "GET", self.endpoint, params=params)
            records = data.get("results", [])
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if exc.response.status_code in {401, 403} else "request_failed"
            raise ProviderError(f"OpenAlex HTTP {exc.response.status_code}", code=code) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("OpenAlex request failed", code="request_failed") from exc

        candidates: list[ReferenceCandidate] = []
        for record in records:
            title = (record.get("display_name") or record.get("title") or "").strip()
            if not title:
                continue
            primary_location = record.get("primary_location") or {}
            source = primary_location.get("source") or {}
            doi = record.get("doi")
            candidates.append(
                ReferenceCandidate(
                    source=self.name,
                    source_id=record.get("id"),
                    title=title,
                    abstract=_abstract_from_inverted_index(record.get("abstract_inverted_index")),
                    authors=[
                        authorship.get("author", {}).get("display_name", "").strip()
                        for authorship in record.get("authorships", [])
                        if authorship.get("author", {}).get("display_name")
                    ],
                    year=record.get("publication_year"),
                    journal=source.get("display_name"),
                    doi=doi,
                    url=doi or primary_location.get("landing_page_url") or record.get("id"),
                    publication_type=record.get("type"),
                    volume=(record.get("biblio") or {}).get("volume"),
                    issue=(record.get("biblio") or {}).get("issue"),
                    pages="-".join(
                        str(v)
                        for v in [
                            (record.get("biblio") or {}).get("first_page"),
                            (record.get("biblio") or {}).get("last_page"),
                        ]
                        if v
                    )
                    or None,
                    citations=record.get("cited_by_count") or 0,
                )
            )
        return candidates

    async def close(self) -> None:
        await self.client.aclose()
