from __future__ import annotations

import html
import re
from typing import Any

import httpx

from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError
from autoreference.providers.http import request_json


def _first(value: Any, default: str = "") -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return default


def _plain_abstract(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value))).strip()


def _year(record: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (record.get(key) or {}).get("date-parts")
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


class CrossrefProvider:
    name = "crossref"
    endpoint = "https://api.crossref.org/works"

    def __init__(
        self,
        *,
        headers: dict[str, str],
        contact_email: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.contact_email = contact_email
        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        params: dict[str, str | int] = {"query.bibliographic": query, "rows": limit}
        if self.contact_email:
            params["mailto"] = self.contact_email
        try:
            data = await request_json(self.client, "GET", self.endpoint, params=params)
            records = data.get("message", {}).get("items", [])
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if exc.response.status_code in {401, 403} else "request_failed"
            raise ProviderError(f"Crossref HTTP {exc.response.status_code}", code=code) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Crossref request failed", code="request_failed") from exc

        candidates: list[ReferenceCandidate] = []
        for record in records:
            title = _first(record.get("title")).strip()
            if not title:
                continue
            authors = []
            for author in record.get("author", []):
                name = " ".join(
                    part for part in (author.get("given", ""), author.get("family", "")) if part
                ).strip()
                if name:
                    authors.append(name)
            candidates.append(
                ReferenceCandidate(
                    source=self.name,
                    source_id=record.get("DOI") or record.get("URL"),
                    title=title,
                    abstract=_plain_abstract(record.get("abstract")),
                    authors=authors,
                    year=_year(record),
                    journal=_first(record.get("container-title")) or None,
                    doi=record.get("DOI"),
                    url=record.get("URL"),
                    publication_type=record.get("type"),
                    volume=record.get("volume"),
                    issue=record.get("issue"),
                    pages=record.get("page"),
                    citations=record.get("is-referenced-by-count") or 0,
                )
            )
        return candidates

    async def close(self) -> None:
        await self.client.aclose()
