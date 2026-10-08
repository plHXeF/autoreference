import httpx

from autoreference.providers.http import request_json


async def test_retries_are_bounded_and_respect_delay(monkeypatch):
    delays = []
    calls = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("autoreference.providers.http.asyncio.sleep", sleep)

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "999"})
            if len(calls) < 3
            else httpx.Response(200, json={"results": []})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await request_json(client, "GET", "https://api.example/works")
    assert result == {"results": []}
    assert len(calls) == 3
    assert delays == [5, 5]
