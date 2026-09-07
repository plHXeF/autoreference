from __future__ import annotations

from collections.abc import Callable

from autoreference.config import Settings
from autoreference.llm import LLMClient
from autoreference.providers.base import SearchProvider
from autoreference.providers.crossref import CrossrefProvider
from autoreference.providers.openalex import OpenAlexProvider
from autoreference.service import SearchService


def create_service(
    settings: Settings,
    *,
    include_zhizhen: bool = False,
    lazy_zhizhen: bool = False,
) -> SearchService:
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
    provider_factories: dict[str, Callable[[], SearchProvider]] = {}
    if include_zhizhen:
        from autoreference.providers.zhizhen import ZhizhenProvider

        providers["zhizhen"] = ZhizhenProvider(settings)  # type: ignore[assignment]
    elif lazy_zhizhen:

        def create_zhizhen() -> SearchProvider:
            from autoreference.providers.zhizhen import ZhizhenProvider

            return ZhizhenProvider(settings)

        provider_factories["zhizhen"] = create_zhizhen

    llm = LLMClient(settings) if settings.llm_enabled else None
    return SearchService(providers=providers, llm=llm, provider_factories=provider_factories)
