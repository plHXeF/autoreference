from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from autoreference.config import Settings
from autoreference.models import CitationAssessment, ReferenceCandidate, SearchQueries

QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chinese": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "english": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
    "required": ["chinese", "english"],
    "additionalProperties": False,
}

ASSESSMENT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidate_index": {"type": "integer", "minimum": 0},
        "can_cite": {"type": "boolean"},
        "relevance_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason": {"type": "string"},
        "supporting_points": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "candidate_index",
        "can_cite",
        "relevance_score",
        "reason",
        "supporting_points",
        "caveats",
    ],
    "additionalProperties": False,
}

ASSESSMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"assessments": {"type": "array", "items": ASSESSMENT_ITEM_SCHEMA}},
    "required": ["assessments"],
    "additionalProperties": False,
}


def _extract_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("model response did not contain a JSON object") from None
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response JSON must be an object")
    return value


class LLMClient:
    """Model adapter with Responses API and OpenAI-compatible fallback modes."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=2,
        )

    async def _json_response(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        effort: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        if self.settings.api_mode == "responses":
            response = await self.client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                reasoning={"effort": effort},
                max_output_tokens=max_output_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                    "verbosity": "low",
                },
                store=False,
            )
            return _extract_json(response.output_text)

        completion = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=max_output_tokens,
            extra_body={"reasoning_effort": effort},
        )
        content = completion.choices[0].message.content or ""
        return _extract_json(content)

    async def generate_queries(self, claim: str) -> SearchQueries:
        data = await self._json_response(
            model=self.settings.query_model,
            instructions=(
                "You generate concise scholarly database queries. Return phrases that are likely "
                "to appear in paper titles or abstracts. Preserve technical names. Do not invent "
                "authors, titles, identifiers, or findings."
            ),
            prompt=(
                "Generate up to 3 Chinese and up to 5 English literature-search queries for this "
                f"claim. Each query should contain 2-6 terms. Claim:\n{claim}"
            ),
            schema_name="search_queries",
            schema=QUERY_SCHEMA,
            effort=self.settings.effort_for("query"),
            max_output_tokens=self.settings.query_max_output_tokens,
        )
        return SearchQueries.model_validate(data)

    async def assess_candidates(
        self, claim: str, candidates: list[ReferenceCandidate]
    ) -> list[CitationAssessment]:
        payload = [
            {
                "candidate_index": index,
                "title": candidate.title,
                "abstract": candidate.abstract,
                "year": candidate.year,
                "journal": candidate.journal,
                "doi": candidate.doi,
            }
            for index, candidate in enumerate(candidates)
        ]
        data = await self._json_response(
            model=self.settings.judge_model,
            instructions=(
                "You are a conservative scholarly citation assessor. Decide whether each candidate "
                "actually supports the stated claim using only the supplied metadata. A topical "
                "match is not sufficient. If the abstract is missing or evidence is ambiguous, "
                "lower the score, set can_cite=false when support cannot be established, and state "
                "that full-text verification is required. Never claim to have read unavailable "
                "text."
            ),
            prompt=(
                "Assess every candidate against the claim. Scores mean: 90-100 direct strong "
                "support; 70-89 plausible support requiring source verification; 40-69 related but "
                "insufficient; 0-39 irrelevant. Return one assessment per candidate, preserving "
                "candidate_index.\n\n"
                f"CLAIM:\n{claim}\n\nCANDIDATES:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
            schema_name="citation_assessments",
            schema=ASSESSMENTS_SCHEMA,
            effort=self.settings.effort_for("judge"),
            max_output_tokens=self.settings.judge_max_output_tokens,
        )

        by_index: dict[int, CitationAssessment] = {}
        for item in data.get("assessments", []):
            try:
                index = int(item["candidate_index"])
                by_index[index] = CitationAssessment(
                    **{key: value for key, value in item.items() if key != "candidate_index"},
                    assessed_by=f"{self.settings.judge_model}:{self.settings.effort_for('judge')}",
                )
            except (KeyError, TypeError, ValueError):
                continue

        return [
            by_index.get(
                index,
                CitationAssessment(
                    reason="The model omitted this candidate; manual review is required.",
                    caveats=["Incomplete model output"],
                    assessed_by=self.settings.judge_model,
                ),
            )
            for index in range(len(candidates))
        ]

    async def close(self) -> None:
        await self.client.close()
