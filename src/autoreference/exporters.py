from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata

from autoreference.models import ReferenceCandidate


def _ascii_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "", normalized).lower()


def citation_key(candidate: ReferenceCandidate) -> str:
    author = _ascii_slug(candidate.authors[0].split()[-1]) if candidate.authors else "ref"
    year = str(candidate.year or "nd")
    title_word = next(
        (_ascii_slug(word) for word in candidate.title.split() if _ascii_slug(word)), "paper"
    )
    digest = hashlib.sha1(
        (candidate.doi or candidate.title).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:6]
    return f"{author}{year}{title_word}{digest}"


def _bibtex_escape(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    escapes = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(escapes.get(character, character) for character in value)


def to_bibtex(candidate: ReferenceCandidate) -> str:
    if candidate.bibtex and candidate.bibtex.lstrip().startswith("@"):
        return candidate.bibtex.strip()
    entry_type = {
        "proceedings-article": "inproceedings",
        "conference-paper": "inproceedings",
        "book": "book",
        "book-chapter": "incollection",
    }.get(candidate.publication_type, "article" if candidate.journal else "misc")
    fields: list[tuple[str, str]] = [("title", candidate.title)]
    if candidate.authors:
        fields.append(("author", " and ".join(candidate.authors)))
    if candidate.journal:
        fields.append(
            (
                "booktitle" if entry_type in {"inproceedings", "incollection"} else "journal",
                candidate.journal,
            )
        )
    for name, value in (
        ("volume", candidate.volume),
        ("number", candidate.issue),
        ("pages", candidate.pages),
    ):
        if value:
            fields.append((name, value))
    if candidate.year:
        fields.append(("year", str(candidate.year)))
    if candidate.doi:
        fields.append(("doi", candidate.doi))
    if candidate.url:
        fields.append(("url", candidate.url))
    body = "\n".join(f"  {name} = {{{_bibtex_escape(value)}}}," for name, value in fields)
    return f"@{entry_type}{{{citation_key(candidate)},\n{body}\n}}"


def export_bibtex(candidates: list[ReferenceCandidate]) -> str:
    entries = "\n\n".join(to_bibtex(candidate) for candidate in candidates)
    return entries + ("\n" if candidates else "")


def export_csv(candidates: list[ReferenceCandidate]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        ["citation_key", "title", "authors", "year", "journal", "doi", "url", "source", "score"]
    )
    for candidate in candidates:
        writer.writerow(
            [
                citation_key(candidate),
                candidate.title,
                "; ".join(candidate.authors),
                candidate.year or "",
                candidate.journal or "",
                candidate.doi or "",
                candidate.url or "",
                candidate.source,
                candidate.assessment.relevance_score if candidate.assessment else "",
            ]
        )
    return stream.getvalue()


def export_json(candidates: list[ReferenceCandidate]) -> str:
    return json.dumps(
        [candidate.model_dump(mode="json") for candidate in candidates],
        ensure_ascii=False,
        indent=2,
    )
