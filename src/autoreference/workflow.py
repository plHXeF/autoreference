"""Resumable, model-free task protocol for any shell-capable agent."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from autoreference.config import Settings
from autoreference.documents import parse_document, stable_id
from autoreference.exporters import export_bibtex
from autoreference.factory import create_service
from autoreference.matching import deduplicate, normalized_title, same_record
from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError
from autoreference.text import search_tokens
from autoreference.verification import resolve_reference

SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryItem(StrictModel):
    claim_id: str
    queries: list[str] = Field(min_length=1, max_length=6)
    sources: list[str] | None = None
    limit: int = Field(default=8, ge=1, le=25)


class SearchBatch(StrictModel):
    requests: list[QueryItem] = Field(min_length=1, max_length=20)


class EvidenceInput(StrictModel):
    candidate_id: str
    url: str
    text: str = Field(min_length=1, max_length=100_000)
    kind: str = Field(pattern=r"^(abstract|full_text)$")


class ExistingInput(StrictModel):
    key: str
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None


class Decision(StrictModel):
    claim_id: str
    candidate_id: str
    support: str = Field(pattern=r"^(supported|uncertain|unsupported)$")
    reason: str = Field(min_length=1)
    evidence_id: str | None = None
    quote: str | None = None


class FinalizeInput(StrictModel):
    decisions: list[Decision] = Field(default_factory=list)
    skipped_claims: dict[str, str] = Field(default_factory=dict)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def task_lock(directory: Path):
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "task.lock"
    try:
        descriptor = os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Task is locked by another process; remove task.lock only after it exits."
        ) from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield directory
    finally:
        file.unlink(missing_ok=True)


def load_task(directory: Path) -> dict:
    state = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported task schema version; use the matching tool release.")
    return state


def prepare(directory: Path, *, text: str | None = None, path: Path | None = None) -> dict:
    document = parse_document(text=text, path=path)
    fingerprint = stable_id("input_", json.dumps(document, ensure_ascii=False, sort_keys=True))
    with task_lock(directory) as folder:
        if (folder / "task.json").exists():
            state = load_task(folder)
            if state["fingerprint"] != fingerprint:
                raise ValueError(
                    "This task directory belongs to another input; choose a new directory."
                )
            return state
        if any((folder / name).exists() for name in ("references.bib", "report.json", "report.md")):
            raise ValueError(
                "Output directory contains unmanaged artifacts; choose a new directory."
            )
        state = {
            "schema_version": SCHEMA_VERSION,
            "status": "prepared",
            "fingerprint": fingerprint,
            "document": document,
            "candidates": {},
            "claim_candidates": {},
            "evidence": {},
            "search_runs": [],
            "decisions": [],
            "skipped_claims": {},
            "artifacts": [],
        }
        for ref in document["existing_references"]:
            if ref.get("candidate"):
                candidate = ReferenceCandidate.model_validate(ref["candidate"])
                ref["candidate_id"] = _store_candidate(state, candidate)
        atomic_json(folder / "task.json", state)
        return state


def _add_abstract(state: dict, candidate_id: str, candidate: ReferenceCandidate) -> None:
    if candidate.abstract:
        key = stable_id("e_", candidate_id + candidate.abstract)
        state["evidence"][key] = {
            "candidate_id": candidate_id,
            "kind": "abstract",
            "url": candidate.url or ("https://doi.org/" + candidate.doi if candidate.doi else ""),
            "text": candidate.abstract,
            "origin": "provider",
        }


def _store_candidate(state: dict, candidate: ReferenceCandidate) -> str:
    for key, value in state["candidates"].items():
        current = ReferenceCandidate.model_validate(value)
        if same_record(current, candidate):
            merged = deduplicate([current, candidate])[0]
            state["candidates"][key] = merged.model_dump(mode="json")
            _add_abstract(state, key, candidate)
            return key
    key = stable_id("p_", candidate.doi or normalized_title(candidate.title) + str(candidate.year))
    # Different DOIs remain different records; IDs never depend on list order.
    state["candidates"][key] = candidate.model_dump(mode="json")
    _add_abstract(state, key, candidate)
    return key


async def search_task(
    directory: Path, payload: dict, settings: Settings, *, refresh: bool = False, service=None
) -> dict:
    batch = SearchBatch.model_validate(payload)
    owned_service = service is None
    service = service or create_service(settings, lazy_zhizhen=True, enable_llm=False)
    try:
        with task_lock(directory) as folder:
            state = load_task(folder)
            claims = {c["id"]: c for c in state["document"]["claims"]}
            for item in batch.requests:
                if item.claim_id not in claims or any(
                    not q.strip() or len(q) > 8000 for q in item.queries
                ):
                    raise ValueError("Unknown claim_id or invalid query.")
            semaphore = asyncio.Semaphore(4)
            campus_lock = asyncio.Lock()
            for item in batch.requests:
                sources = item.sources or ["openalex", "crossref"] + (
                    ["anysearch"] if settings.anysearch_api_key else []
                )
                signature = stable_id(
                    "q_", json.dumps(item.model_dump(), sort_keys=True) + str(sources)
                )
                if not refresh and any(run["id"] == signature for run in state["search_runs"]):
                    continue

                async def run(source: str, query: str, limit: int) -> tuple[dict, list]:
                    async with semaphore:
                        try:
                            provider = service._get_provider(source)
                            if not provider:
                                return {
                                    "source": source,
                                    "query": query,
                                    "status": "unconfigured",
                                }, []
                            if source == "zhizhen":
                                async with campus_lock:
                                    results = await provider.search(query, limit)
                            else:
                                results = await provider.search(query, limit)
                            return {
                                "source": source,
                                "query": query,
                                "status": "success" if results else "empty",
                                "count": len(results),
                            }, results
                        except Exception as exc:
                            code = exc.code if isinstance(exc, ProviderError) else "request_failed"
                            # Never serialize exception URLs/headers; they may contain API keys.
                            return {"source": source, "query": query, "status": code}, []

                outcomes = await asyncio.gather(
                    *(
                        run(s, q.strip(), item.limit)
                        for s in dict.fromkeys(sources)
                        for q in dict.fromkeys(item.queries)
                    )
                )
                candidates = deduplicate(c for _, results in outcomes for c in results)
                stopwords = {"the", "and", "for", "with", "using", "based", "of", "in", "on"}
                query_tokens = [search_tokens(q) - stopwords for q in item.queries]
                tokens = set().union(*query_tokens)
                before_filter = len(candidates)
                candidates = [
                    c
                    for c in candidates
                    if any(
                        len(t) < 2 or len(t & search_tokens(c.title + " " + c.abstract)) >= 2
                        for t in query_tokens
                    )
                ]
                candidates.sort(
                    key=lambda c: (
                        len(tokens & search_tokens(c.title + " " + c.abstract)),
                        c.citations,
                    ),
                    reverse=True,
                )
                keys = state["claim_candidates"].setdefault(item.claim_id, [])
                for candidate in candidates:
                    key = _store_candidate(state, candidate)
                    if key not in keys:
                        keys.append(key)
                state["search_runs"].append(
                    {
                        "id": signature,
                        "claim_id": item.claim_id,
                        "outcomes": [o for o, _ in outcomes],
                        "filtered_irrelevant": before_filter - len(candidates),
                    }
                )
                # Checkpoint each completed claim; interrupted batches retain previous claims.
                state["status"] = "searched"
                atomic_json(folder / "task.json", state)
            outcomes = [o for run in state["search_runs"] for o in run["outcomes"]]
            failures = [o for o in outcomes if o["status"] not in {"success", "empty"}]
            usable = any(o["status"] in {"success", "empty"} for o in outcomes)
            campus_action = any(
                o["source"] == "zhizhen"
                and o["status"]
                in {"requires_login", "access_denied", "network_required", "browser_unavailable"}
                for o in failures
            )
            state["protocol_status"] = (
                "needs_user_action"
                if campus_action
                else "partial"
                if failures and usable
                else "failed"
                if failures
                else "success"
            )
            atomic_json(folder / "task.json", state)
            return state
    finally:
        if owned_service:
            await service.close()


async def verify_task(
    directory: Path,
    settings: Settings,
    *,
    evidence: list[dict] | None = None,
    references: list[dict] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    external = [EvidenceInput.model_validate(e) for e in evidence or []]
    existing_input = [ExistingInput.model_validate(r) for r in references or []]
    owned_client = client is None
    client = client or httpx.AsyncClient(
        headers=settings.public_api_headers(), timeout=settings.request_timeout_seconds
    )
    try:
        with task_lock(directory) as folder:
            state = load_task(folder)
            refs_by_key = {r["key"]: r for r in state["document"]["existing_references"]}
            for item in existing_input:
                ref = refs_by_key.get(item.key)
                if not ref or not ref.get("raw"):
                    raise ValueError("Reference extraction requires an existing raw reference key.")
                if normalized_title(item.title) not in normalized_title(ref["raw"]):
                    raise ValueError("Extracted title must occur in the original reference text.")
                if any(
                    normalized_title(a) not in normalized_title(ref["raw"]) for a in item.authors
                ):
                    raise ValueError("Extracted authors must occur in the original reference text.")
                if item.year and str(item.year) not in ref["raw"]:
                    raise ValueError("Extracted year must occur in the original reference text.")
                if item.doi and normalized_title(item.doi) not in normalized_title(ref["raw"]):
                    raise ValueError("Extracted DOI must occur in the original reference text.")
                candidate = ReferenceCandidate(
                    source="document", source_id=item.key, **item.model_dump(exclude={"key"})
                )
                ref["candidate_id"] = _store_candidate(state, candidate)
                ref["candidate"] = candidate.model_dump(mode="json")
            for item in external:
                if item.candidate_id not in state["candidates"]:
                    raise ValueError("Evidence refers to an unknown candidate_id.")
                if urlparse(item.url).scheme not in {"http", "https"}:
                    raise ValueError("Evidence URL must use HTTP or HTTPS.")
                key = stable_id("e_", item.candidate_id + item.url + item.text)
                state["evidence"][key] = {**item.model_dump(), "origin": "agent_supplied"}
            for key, value in list(state["candidates"].items()):
                candidate = ReferenceCandidate.model_validate(value)
                if candidate.metadata_status == "verified":
                    continue
                try:
                    resolved = await resolve_reference(client, candidate=candidate)
                    if resolved:
                        state["candidates"][key] = resolved.model_dump(mode="json")
                        _add_abstract(state, key, resolved)
                except (httpx.HTTPError, ValueError):
                    candidate.verification = {
                        "status": "unavailable",
                        "reason": "Metadata lookup failed",
                    }
                    state["candidates"][key] = candidate.model_dump(mode="json")
                atomic_json(folder / "task.json", state)
            for ref in state["document"]["existing_references"]:
                if ref.get("candidate_id"):
                    continue
                try:
                    resolved = await resolve_reference(
                        client, raw=ref.get("raw"), doi_hint=ref.get("doi_hint")
                    )
                    if resolved:
                        ref["candidate_id"] = _store_candidate(state, resolved)
                        ref["resolution"] = "verified"
                    else:
                        ref["resolution"] = "unresolved"
                except (httpx.HTTPError, ValueError):
                    ref["resolution"] = "unavailable"
                atomic_json(folder / "task.json", state)
            state["status"] = "verified"
            atomic_json(folder / "task.json", state)
            return state
    finally:
        if owned_client:
            await client.aclose()


def finalize(directory: Path, payload: dict) -> dict:
    batch = FinalizeInput.model_validate(payload)
    with task_lock(directory) as folder:
        state = load_task(folder)
        claims = {c["id"] for c in state["document"]["claims"]}
        if any(c not in claims or not reason.strip() for c, reason in batch.skipped_claims.items()):
            raise ValueError("Skipped claims require a known claim_id and nonempty reason.")
        previous = {(d["claim_id"], d["candidate_id"]): d for d in state["decisions"]}
        for decision in batch.decisions:
            if decision.claim_id not in claims or decision.candidate_id not in state["candidates"]:
                raise ValueError("Decision contains an unknown claim_id or candidate_id.")
            if decision.candidate_id not in state["claim_candidates"].get(decision.claim_id, []):
                raise ValueError("Candidate was not retrieved for this claim.")
            if decision.support == "supported":
                ev = state["evidence"].get(decision.evidence_id)
                if not ev or ev["candidate_id"] != decision.candidate_id or not ev.get("url"):
                    raise ValueError(
                        "Supported decisions require attributable evidence for this candidate."
                    )
                if (
                    not decision.quote
                    or len(decision.quote.strip()) < 12
                    or decision.quote not in ev["text"]
                ):
                    raise ValueError(
                        "Quote must be an exact, nontrivial passage from recorded evidence."
                    )
            previous[(decision.claim_id, decision.candidate_id)] = decision.model_dump()
        state["decisions"] = list(previous.values())
        state["skipped_claims"].update(batch.skipped_claims)
        selected: dict[str, ReferenceCandidate] = {}
        existing = []
        unresolved_existing = []
        for ref in state["document"]["existing_references"]:
            key = ref.get("candidate_id")
            if key:
                candidate = ReferenceCandidate.model_validate(state["candidates"][key])
                # Preserve original parsed BibTeX rather than guess or silently overwrite fields.
                if ref.get("candidate"):
                    candidate.bibtex = ref["candidate"].get("bibtex")
                selected[key] = candidate
                existing.append(
                    {
                        "key": ref["key"],
                        "candidate_id": key,
                        "metadata_status": candidate.metadata_status,
                    }
                )
            else:
                unresolved_existing.append(ref)
        recommended = []
        supported_claims = set()
        for decision in state["decisions"]:
            candidate = ReferenceCandidate.model_validate(
                state["candidates"][decision["candidate_id"]]
            )
            if decision["support"] == "supported" and candidate.metadata_status == "verified":
                selected.setdefault(decision["candidate_id"], candidate)
                recommended.append(decision)
                supported_claims.add(decision["claim_id"])
        unresolved_claims = sorted(claims - supported_claims - state["skipped_claims"].keys())
        entries = []
        used_keys: set[str] = set()
        citation_keys = {}
        from autoreference.exporters import citation_key

        for candidate_id, candidate in selected.items():
            refs = [
                r
                for r in state["document"]["existing_references"]
                if r.get("candidate_id") == candidate_id
            ]
            # Keep aliases if the original manuscript refers to the same record under two keys.
            keys = [r["key"] for r in refs] or [citation_key(candidate)]
            for key in keys:
                original = key
                while key in used_keys:
                    key = original + "_" + hashlib.sha256(candidate_id.encode()).hexdigest()[:6]
                    if key in used_keys:
                        raise ValueError("Citation key collision could not be resolved.")
                used_keys.add(key)
                copy = candidate.model_copy(deep=True)
                if copy.bibtex:
                    import bibtexparser

                    database = bibtexparser.loads(copy.bibtex)
                    if len(database.entries) != 1:
                        raise ValueError("Existing BibTeX must contain exactly one valid entry.")
                    database.entries[0]["ID"] = key
                    copy.bibtex = bibtexparser.dumps(database)
                    entries.append(copy.bibtex.strip())
                else:
                    rendered = export_bibtex([copy])
                    rendered = rendered.replace("{" + citation_key(copy) + ",", "{" + key + ",", 1)
                    entries.append(rendered.strip())
                citation_keys.setdefault(candidate_id, []).append(key)
        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "partial" if unresolved_claims or unresolved_existing else "success",
            "existing": existing,
            "recommended": recommended,
            "citation_keys": citation_keys,
            "unresolved_existing": unresolved_existing,
            "unresolved_claims": unresolved_claims,
            "skipped_claims": state["skipped_claims"],
            "decisions": state["decisions"],
            "candidates": state["candidates"],
            "evidence": state["evidence"],
            "claims": state["document"]["claims"],
            "search_runs": state["search_runs"],
            "warnings": state["document"]["warnings"],
            "assessment_note": "Agent support judgments are not independently proven by this tool.",
        }
        artifacts = ["references.bib", "report.json", "report.md"]
        for name in artifacts:
            if (folder / name).exists() and name not in state["artifacts"]:
                raise ValueError(f"Refusing to overwrite unmanaged artifact: {name}")
        state["artifacts"] = artifacts
        # Mark ownership before writes so interrupted finalization is safely repeatable.
        atomic_json(folder / "task.json", state)
        (folder / "references.bib").write_text(
            "\n\n".join(entries) + ("\n" if entries else ""), encoding="utf-8"
        )
        atomic_json(folder / "report.json", report)
        lines = [
            "# AutoReference report",
            "",
            f"Status: {report['status']}",
            f"Existing references: {len(existing)}; new recommendations: {len(recommended)}",
            f"Unresolved claims: {len(unresolved_claims)}; "
            f"unresolved references: {len(unresolved_existing)}",
            "",
            report["assessment_note"],
            "",
            "## Claim decisions",
            "",
        ]
        for decision in state["decisions"]:
            lines.append(
                f"- {decision['claim_id']} → {decision['candidate_id']}: "
                f"{decision['support']}. {decision['reason']}"
            )
        lines += ["", "## Unresolved claims", ""]
        lines += [
            f"- {c['id']}: {c['text']}"
            for c in state["document"]["claims"]
            if c["id"] in unresolved_claims
        ]
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in report["warnings"]]
        (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name in artifacts:
            os.chmod(folder / name, 0o600)
        state["status"] = "finalized"
        atomic_json(folder / "task.json", state)
        return {
            "status": report["status"],
            "artifacts": {name: str(folder / name) for name in artifacts},
            "reference_count": len(entries),
            "unresolved_claims": unresolved_claims,
            "unresolved_existing_count": len(unresolved_existing),
        }
