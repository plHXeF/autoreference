"""AnySearch Academic JSON-RPC adapter; no dependence on an installed MCP client."""

from __future__ import annotations

import json
import re

import httpx

from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError
from autoreference.providers.http import request_json


def markdown_records(text: str) -> list[dict]:
    headings = list(re.finditer(r"(?m)^###\s+\d+[.)]\s+(.+)$", text))
    records = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[heading.end() : end]
        fields = {
            key.lower().strip(): value.strip()
            for key, value in re.findall(r"(?m)^-\s+\*\*(.+?)\*\*:\s*(.+)$", block)
        }
        doi = re.search(r"10\.\d{4,9}/[^\s<>\])]+", block)
        year = re.search(r"\b(?:18|19|20)\d{2}\b", fields.get("published", fields.get("year", "")))
        records.append(
            {
                "title": heading[1].strip(),
                **fields,
                "doi": doi[0].rstrip(".,;") if doi else fields.get("doi"),
                "year": int(year[0]) if year else None,
            }
        )
    return records


def parse_response(data: dict) -> list[ReferenceCandidate]:
    if data.get("error"):
        raise ProviderError("AnySearch JSON-RPC error", code="service_error")
    result = data.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ProviderError("AnySearch returned an invalid tool result", code="parse_error")
    raw = []
    content = result.get("content", [])
    if not isinstance(content, list):
        raise ProviderError("AnySearch content is not a list", code="parse_error")
    for item in content:
        text = item.get("text", "")
        if not text:
            continue
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                raw.extend(decoded)
            elif isinstance(decoded, dict):
                items = decoded.get("results", decoded.get("papers"))
                raw.extend(items if isinstance(items, list) else [decoded])
        except json.JSONDecodeError:
            records = markdown_records(text)
            if not records and not re.search(r"no (?:results|papers)|未找到|没有结果", text, re.I):
                raise ProviderError(
                    "Unrecognized AnySearch response format", code="parse_error"
                ) from None
            raw.extend(records)
    candidates = []
    for record in raw:
        if not isinstance(record, dict):
            raise ProviderError("Invalid AnySearch record", code="parse_error")
        title = record.get("title") or record.get("display_name")
        if not title:
            raise ProviderError("AnySearch record has no title", code="parse_error")
        authors = record.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in re.split(r";|\s+and\s+|,", authors) if a.strip()]
        authors = [
            a.get("name", a.get("display_name", "")) if isinstance(a, dict) else str(a)
            for a in authors
        ]
        year = record.get("year", record.get("publication_year"))
        try:
            year = int(str(year)[:4]) if year else None
            count = int(
                str(record.get("citations", record.get("cited_by_count", 0))).replace(",", "")
            )
        except ValueError as exc:
            raise ProviderError("Invalid AnySearch numeric metadata", code="parse_error") from exc
        candidates.append(
            ReferenceCandidate(
                source="anysearch",
                source_id=record.get("id"),
                title=title,
                authors=authors,
                year=year,
                citations=count,
                doi=record.get("doi"),
                abstract=record.get("abstract") or record.get("summary") or "",
                journal=record.get("journal") or record.get("venue"),
                url=record.get("url") or record.get("link"),
                volume=str(record["volume"]) if record.get("volume") else None,
                issue=str(record["issue"]) if record.get("issue") else None,
                pages=str(record["pages"]) if record.get("pages") else None,
            )
        )
    return candidates


class AnySearchProvider:
    name = "anysearch"
    endpoint = "https://api.anysearch.com/mcp"

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client = httpx.AsyncClient(
            timeout=timeout, transport=transport, headers={"Authorization": f"Bearer {api_key}"}
        )

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {
                    "query": query,
                    "domain": "academic",
                    "sub_domain": "academic.search",
                    "content_types": ["academic"],
                    "max_results": limit,
                },
            },
        }
        try:
            data = await request_json(self.client, "POST", self.endpoint, json=payload)
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if exc.response.status_code in {401, 403} else "request_failed"
            raise ProviderError(f"AnySearch HTTP {exc.response.status_code}", code=code) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("AnySearch request failed", code="request_failed") from exc
        return parse_response(data)[:limit]

    async def close(self) -> None:
        await self.client.aclose()
