import json

import bibtexparser
import httpx
import pytest
from typer.testing import CliRunner

from autoreference.cli import app
from autoreference.config import Settings
from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError
from autoreference.service import SearchService
from autoreference.workflow import finalize, load_task, prepare, search_task, verify_task

TITLE = "Shifted windows build cross-window context"
ABSTRACT = "Shifted windows establish cross-window connections in a hierarchical transformer."
RECORD = {
    "DOI": "10.1234/context",
    "title": [TITLE],
    "author": [{"given": "Jane", "family": "Doe"}],
    "issued": {"date-parts": [[2021]]},
    "container-title": ["Test Journal"],
    "URL": "https://doi.org/10.1234/context",
    "volume": "2",
    "issue": "1",
    "page": "1-9",
}


class FakeProvider:
    name = "openalex"
    calls = 0

    async def search(self, query, limit):
        self.calls += 1
        return [
            ReferenceCandidate(
                source=self.name,
                title=TITLE,
                authors=["Jane Doe"],
                year=2021,
                doi="10.1234/context",
                abstract=ABSTRACT,
                url="https://doi.org/10.1234/context",
            )
        ]

    async def close(self):
        pass


async def fixture_task(tmp_path):
    task = tmp_path / "task"
    state = prepare(task, text="Shifted windows establish cross-window connections.")
    claim = state["document"]["claims"][0]["id"]
    provider = FakeProvider()
    service = SearchService({"openalex": provider})
    request = {
        "requests": [
            {"claim_id": claim, "queries": ["shifted windows context"], "sources": ["openalex"]}
        ]
    }
    await search_task(task, request, Settings(), service=service)
    return task, claim, provider, service, request


async def test_resume_verified_evidence_and_bibtex(tmp_path):
    task, claim, provider, service, request = await fixture_task(tmp_path)
    await search_task(task, request, Settings(), service=service)
    assert provider.calls == 1
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"message": RECORD}))
    )
    try:
        state = await verify_task(task, Settings(), client=client)
    finally:
        await client.aclose()
    key = next(iter(state["candidates"]))
    evidence = next(iter(state["evidence"]))
    result = finalize(
        task,
        {
            "decisions": [
                {
                    "claim_id": claim,
                    "candidate_id": key,
                    "support": "supported",
                    "reason": "The abstract states the mechanism.",
                    "evidence_id": evidence,
                    "quote": "Shifted windows establish cross-window connections",
                }
            ]
        },
    )
    assert result["status"] == "success"
    database = bibtexparser.loads((task / "references.bib").read_text())
    assert database.entries[0]["doi"] == "10.1234/context"
    assert database.entries[0]["volume"] == "2"
    assert database.entries[0]["number"] == "1"
    assert database.entries[0]["pages"] == "1-9"
    assert finalize(task, {"decisions": []})["reference_count"] == 1


async def test_unverified_or_unsupported_candidates_not_exported(tmp_path):
    task, claim, _, _, _ = await fixture_task(tmp_path)
    state = load_task(task)
    key = next(iter(state["candidates"]))
    result = finalize(
        task,
        {
            "decisions": [
                {
                    "claim_id": claim,
                    "candidate_id": key,
                    "support": "uncertain",
                    "reason": "Insufficient evidence.",
                }
            ]
        },
    )
    assert result["status"] == "partial"
    assert result["reference_count"] == 0
    with pytest.raises(ValueError, match="evidence"):
        finalize(
            task,
            {
                "decisions": [
                    {
                        "claim_id": claim,
                        "candidate_id": key,
                        "support": "supported",
                        "reason": "Title looks related.",
                    }
                ]
            },
        )


async def test_fabricated_quote_rejected(tmp_path):
    task, claim, _, _, _ = await fixture_task(tmp_path)
    state = load_task(task)
    key = next(iter(state["candidates"]))
    evidence = next(iter(state["evidence"]))
    with pytest.raises(ValueError, match="Quote"):
        finalize(
            task,
            {
                "decisions": [
                    {
                        "claim_id": claim,
                        "candidate_id": key,
                        "support": "supported",
                        "reason": "A reason",
                        "evidence_id": evidence,
                        "quote": "Invented full-text conclusion that does not exist",
                    }
                ]
            },
        )


def test_existing_bibtex_keys_aliases_and_chinese_are_preserved(tmp_path):
    file = tmp_path / "paper.tex"
    (tmp_path / "refs.bib").write_text(
        "@article{oldkey,title={中文论文},author={张三},year={2020}}"
    )
    file.write_text(
        r"\begin{document}Existing claim \cite{oldkey}.\bibliography{refs}\end{document}"
    )
    state = prepare(tmp_path / "task", path=file)
    skipped = {
        c["id"]: "Already cited; no new support judgment." for c in state["document"]["claims"]
    }
    result = finalize(tmp_path / "task", {"skipped_claims": skipped})
    assert result["reference_count"] == 1
    bib = bibtexparser.loads((tmp_path / "task" / "references.bib").read_text())
    assert bib.entries[0]["ID"] == "oldkey"
    assert bib.entries[0]["author"] == "张三"
    report = json.loads((tmp_path / "task" / "report.json").read_text())
    assert report["existing"][0]["metadata_status"] == "unverified"


def test_output_protection_and_stable_ids(tmp_path):
    task = tmp_path / "task"
    first = prepare(task, text="A valid claim.")
    assert prepare(task, text="A valid claim.")["document"] == first["document"]
    with pytest.raises(ValueError, match="another input"):
        prepare(task, text="Another claim.")
    (task / "references.bib").write_text("private original bibliography")
    with pytest.raises(ValueError, match="unmanaged"):
        finalize(task, {})
    assert (task / "references.bib").read_text() == "private original bibliography"


async def test_failure_and_campus_fallback(tmp_path):
    class FailingProvider:
        async def search(self, query, limit):
            raise ProviderError("Private key must not leak", code="requires_login")

    state = prepare(tmp_path / "task", text="A valid claim.")
    claim = state["document"]["claims"][0]["id"]
    service = SearchService({"openalex": FakeProvider(), "zhizhen": FailingProvider()})
    result = await search_task(
        tmp_path / "task",
        {
            "requests": [
                {"claim_id": claim, "queries": ["context"], "sources": ["openalex", "zhizhen"]}
            ]
        },
        Settings(),
        service=service,
    )
    assert result["protocol_status"] == "needs_user_action"
    assert result["candidates"]
    assert "Private key" not in json.dumps(result)
    result = await search_task(
        tmp_path / "task",
        {"requests": [{"claim_id": claim, "queries": ["context"], "sources": ["unknown"]}]},
        Settings(),
        service=service,
    )
    assert result["search_runs"][-1]["outcomes"][0]["status"] == "unconfigured"


def test_json_cli_does_not_require_model_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        app, ["task", "prepare", "--text", "A valid claim.", "--output", str(tmp_path / "task")]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "success"
    error = runner.invoke(app, ["task", "prepare", "--output", str(tmp_path / "other")])
    assert error.exit_code == 1
    assert json.loads(error.stdout)["status"] == "failed"
