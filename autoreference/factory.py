from __future__ import annotations

from autoreference.config import Settings
from autoreference.llm import LLMClient
from autoreference.providers.crossref import CrossrefProvider
from autoreference.providers.openalex import OpenAlexProvider
from autoreference.service import SearchService


def create_service(settings: Settings, *, include_zhizhen: bool = False) -> SearchService:
    headers = settings.public_api_headers()
    providers = {
        "openalex": OpenAlexProvider(
            headers=headers,
            contact_email=settings.contact_email,
            timeout=settings.request_timeout_seconds,
        ),
        "crossref": CrossrefProvider(
            headers=headers,
            contact_email=settings.contact_email,
            timeout=settings.request_timeout_seconds,
        ),
    }
    if include_zhizhen:
        from autoreference.providers.zhizhen import ZhizhenProvider

        providers["zhizhen"] = ZhizhenProvider(settings)  # type: ignore[assignment]

    llm = LLMClient(settings) if settings.llm_enabled else None
    return SearchService(providers=providers, llm=llm)

