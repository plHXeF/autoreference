from __future__ import annotations

from collections.abc import Callable

from autoreference.config import Settings
from autoreference.providers.anysearch import AnySearchProvider
from autoreference.providers.base import SearchProvider
from autoreference.providers.crossref import CrossrefProvider
from autoreference.providers.openalex import OpenAlexProvider
from autoreference.service import SearchService


def create_service(
    settings: Settings,
    *,
    include_zhizhen: bool = False,
    lazy_zhizhen: bool = False,
    enable_llm: bool = True,
) -> SearchService:
    headers = settings.public_api_headers()
    providers = {
        "openalex": OpenAlexProvider(
            headers=headers,
            contact_email=settings.contact_email,
            timeout=settings.request_timeout_seconds,
            api_key=settings.openalex_api_key,
        ),
        "crossref": CrossrefProvider(
            headers=headers,
            contact_email=settings.contact_email,
            timeout=settings.request_timeout_seconds,
        ),
    }
    if settings.anysearch_api_key:
        providers["anysearch"] = AnySearchProvider(
            api_key=settings.anysearch_api_key, timeout=settings.request_timeout_seconds
        )
    provider_factories: dict[str, Callable[[], SearchProvider]] = {}
    if include_zhizhen:
        from autoreference.providers.zhizhen import ZhizhenProvider

        providers["zhizhen"] = ZhizhenProvider(settings)  # type: ignore[assignment]
    elif lazy_zhizhen:

        def create_zhizhen() -> SearchProvider:
            from autoreference.providers.zhizhen import ZhizhenProvider

            return ZhizhenProvider(settings)

        provider_factories["zhizhen"] = create_zhizhen

    llm = None
    if enable_llm and settings.llm_enabled:
        try:
            from autoreference.llm import LLMClient
        except ImportError as exc:
            raise RuntimeError("Install autoreference[llm] to use the model API.") from exc
        llm = LLMClient(settings)
    return SearchService(providers=providers, llm=llm, provider_factories=provider_factories)
