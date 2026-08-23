import httpx
from openai import AsyncOpenAI

from autoreference.config import Settings
from autoreference.llm import LLMClient


async def test_responses_api_uses_structured_output_and_reasoning_budget() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-5.6-luna",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"chinese":["岩芯分析"],"english":["core analysis"]}',
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    settings = Settings(openai_api_key="test-key")
    llm = LLMClient(settings)
    await llm.client.close()
    llm.client = AsyncOpenAI(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        result = await llm.generate_queries("岩芯图像可以用于地质分析。")
    finally:
        await llm.close()

    assert result.chinese == ["岩芯分析"]
    assert captured["reasoning"] == {"effort": "low"}
    assert captured["max_output_tokens"] == 4_000
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["store"] is False

