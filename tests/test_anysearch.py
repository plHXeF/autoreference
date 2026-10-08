import json

import httpx
import pytest

from autoreference.providers.anysearch import AnySearchProvider, parse_response
from autoreference.providers.base import ProviderError


def test_json_and_markdown_formats():
    json_response = {
        "result": {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "results": [
                                {
                                    "title": "A paper",
                                    "authors": ["A Person"],
                                    "year": 2020,
                                    "doi": "10.1234/x",
                                }
                            ]
                        }
                    )
                }
            ]
        }
    }
    assert parse_response(json_response)[0].authors == ["A Person"]
    markdown = (
        "### 1. A paper\n- **URL**: https://doi.org/10.1234/x\n"
        "- **Published**: 2020\n- **Abstract**: A summary\n"
    )
    record = parse_response({"result": {"content": [{"text": markdown}]}})[0]
    assert record.doi == "10.1234/x"
    assert record.abstract == "A summary"


def test_failure_is_not_an_empty_result():
    for value in (
        {"error": {"message": "bad"}},
        {"result": {"content": [{"text": "Changed response format"}]}},
    ):
        with pytest.raises(ProviderError):
            parse_response(value)
    assert parse_response({"result": {"content": [{"text": "[]"}]}}) == []


async def test_auth_failure_is_classified_and_key_not_exposed():
    provider = AnySearchProvider(
        api_key="private-key", transport=httpx.MockTransport(lambda request: httpx.Response(401))
    )
    try:
        with pytest.raises(ProviderError) as captured:
            await provider.search("test", 5)
        assert captured.value.code == "auth_required"
        assert "private-key" not in str(captured.value)
    finally:
        await provider.close()
