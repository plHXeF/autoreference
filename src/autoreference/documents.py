"""Read research documents without executing them or changing their contents."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import bibtexparser
from defusedxml import ElementTree as ET
from pylatexenc.latex2text import LatexNodes2Text

from autoreference.models import ReferenceCandidate
from autoreference.text import split_sentences

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REFERENCE_HEADING = re.compile(r"^(references|bibliography|参考文献)\s*[:：]?\s*$", re.I)
DOI = re.compile(r"10\.\d{4,9}/[^\s<>\"{}]+", re.I)


def stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:16]


def read_bibtex(text: str, warnings: list[str]) -> list[dict]:
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    database = bibtexparser.loads(text, parser=parser)
    entries = []
    seen: set[str] = set()
    for entry in database.entries:
        key = entry["ID"]
        if key in seen:
            warnings.append(f"Duplicate citation key: {key}; preserved first entry.")
            continue
        seen.add(key)
        if not entry.get("title"):
            warnings.append(f"Unresolved BibTeX entry without title: {key}")
            continue
        single = bibtexparser.bibdatabase.BibDatabase()
        single.entries = [entry]
        doi = entry.get("doi")
        item = ReferenceCandidate(
            source="document",
            source_id=key,
            title=entry["title"],
            authors=entry.get("author", "").split(" and ") if entry.get("author") else [],
            year=int(entry["year"]) if entry.get("year", "").isdigit() else None,
            journal=entry.get("journal") or entry.get("booktitle"),
            doi=doi,
            url=entry.get("url"),
            bibtex=bibtexparser.dumps(single),
            volume=entry.get("volume"),
            issue=entry.get("number"),
            pages=entry.get("pages"),
            publication_type={
                "article": "journal-article",
                "inproceedings": "proceedings-article",
                "book": "book",
                "incollection": "book-chapter",
            }.get(entry["ENTRYTYPE"]),
        )
        entries.append({"key": key, "candidate": item.model_dump(mode="json")})
    # Do not silently accept a parser that recovered only part of a file.
    count = len(re.findall(r"@(?!(?:comment|string|preamble)\b)[\w-]+\s*[{(]", text, re.I))
    if count != len(database.entries):
        warnings.append("Some BibTeX entries could not be parsed; inspect the original file.")
    return entries


def _plain_references(lines: list[str], warnings: list[str]) -> list[dict]:
    """Only structured BibTeX is exported automatically; raw citations need resolution."""
    entries = []
    numbered = any(re.match(r"\s*\[[^]]+\]|\s*\d+[.)]\s", line) for line in lines)
    blocks: list[str] = []
    for line in lines:
        marker = re.match(r"\s*\[[^]]+\]|\s*\d+[.)]\s", line)
        if numbered and not marker and blocks and line.strip():
            blocks[-1] += " " + line.strip()
        elif line.strip():
            blocks.append(line.strip())
    for index, line in enumerate(blocks, 1):
        if not line.strip():
            continue
        key_match = re.match(r"\s*\[([^]]+)\]\s*|\s*(\d+)[.)]\s", line)
        doi = DOI.search(line)
        entries.append(
            {
                "key": (key_match[1] or key_match[2]) if key_match else f"existing{index}",
                "raw": line,
                "doi_hint": doi[0].rstrip(".,;") if doi else None,
                "candidate": None,
            }
        )
    if entries:
        warnings.append("Unstructured references require metadata resolution; no fields guessed.")
    return entries


def _docx(path: Path, warnings: list[str]) -> tuple[list[tuple[str, str]], list[dict]]:
    paragraphs = []
    references = []
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 50_000_000:
            raise ValueError("DOCX exceeds the 50 MB uncompressed input limit.")
        for part in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml"):
            if part not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(part))
            for index, p in enumerate(root.iter(W + "p"), 1):
                value = "".join(n.text or "" for n in p.iter(W + "t"))
                fields = " ".join(n.text or "" for n in p.iter(W + "instrText"))
                fields += " ".join(n.get(W + "instr", "") for n in p.iter(W + "fldSimple"))
                if fields:
                    parsed_field = False
                    if "CSL_CITATION" in fields and "{" in fields:
                        try:
                            payload, _ = json.JSONDecoder().raw_decode(fields[fields.index("{") :])
                            for citation in payload.get("citationItems", []):
                                data = citation.get("itemData", {})
                                if not data.get("title"):
                                    continue
                                key = stable_id("existing_", str(citation.get("id", data)))
                                issued = data.get("issued", {}).get("date-parts", [[]])
                                candidate = ReferenceCandidate(
                                    source="document",
                                    source_id=key,
                                    title=data["title"],
                                    authors=[
                                        " ".join(
                                            filter(
                                                None,
                                                [a.get("given"), a.get("family"), a.get("literal")],
                                            )
                                        )
                                        for a in data.get("author", [])
                                    ],
                                    year=issued[0][0] if issued and issued[0] else None,
                                    doi=data.get("DOI"),
                                    journal=data.get("container-title"),
                                    url=data.get("URL"),
                                    volume=data.get("volume"),
                                    issue=data.get("issue"),
                                    pages=data.get("page"),
                                )
                                references.append(
                                    {"key": key, "candidate": candidate.model_dump(mode="json")}
                                )
                                value += f" [cite:{key}]"
                                parsed_field = True
                        except (ValueError, TypeError, KeyError):
                            pass
                    if not parsed_field:
                        warnings.append(f"Unrecognized citation field at {part}:{index}: {fields}")
                if value.strip():
                    paragraphs.append((f"{part}:{index}", value.strip()))
    return paragraphs, references


def _tex(path: Path, warnings: list[str]) -> tuple[list[tuple[str, str]], list[dict], dict]:
    project_root = path.parent.resolve()
    active: set[Path] = set()
    seen_bibs: set[Path] = set()
    references: list[dict] = []
    paragraphs: list[tuple[str, str]] = []
    source_hashes = {}
    converter = LatexNodes2Text()

    def resolve(name: str, suffix: str, parent: Path) -> Path | None:
        target = (parent / name).with_suffix(suffix) if not Path(name).suffix else parent / name
        target = target.resolve()
        if not target.is_relative_to(project_root):
            warnings.append(f"Blocked project-external path: {name}")
            return None
        if not target.is_file():
            warnings.append(f"Missing project file: {name}")
            return None
        return target

    def visit(file: Path) -> None:
        if file in active:
            warnings.append(f"Circular TeX include: {file.name}")
            return
        active.add(file)
        source_hashes[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
        text = re.sub(r"(?<!\\)%[^\n]*", "", file.read_text(encoding="utf-8"))
        # Ignore preamble before the document environment, but retain bibliography declarations.
        bib_pattern = r"\\(?:bibliography|addbibresource)(?:\[[^]]*\])?\{([^}]+)\}"
        for names in re.findall(bib_pattern, text):
            for name in names.split(","):
                bib = resolve(name.strip(), ".bib", file.parent)
                if bib and bib not in seen_bibs:
                    seen_bibs.add(bib)
                    source_hashes[str(bib)] = hashlib.sha256(bib.read_bytes()).hexdigest()
                    references.extend(read_bibtex(bib.read_text(encoding="utf-8"), warnings))
        text = re.sub(bib_pattern, "", text)
        for body in re.findall(
            r"\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}", text, re.S
        ):
            for key, value in re.findall(
                r"\\bibitem(?:\[[^]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\Z)", body, re.S
            ):
                references.append(
                    {"key": key, "raw": converter.latex_to_text(value).strip(), "candidate": None}
                )
        text = re.sub(
            r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "", text, flags=re.S
        )
        if "\\begin{document}" in text:
            text = text.split("\\begin{document}", 1)[1]
        text = text.split("\\end{document}", 1)[0]
        pattern = re.compile(r"\\(?:input|include)\{([^}]+)\}")
        start = 0

        def add(chunk: str, offset: int) -> None:
            chunk = re.sub(
                r"\\(?:cite\w*|nocite)\*?(?:\[[^]]*\])*\{([^}]+)\}",
                lambda m: " [cite:" + m[1] + "] ",
                chunk,
            )
            for index, part in enumerate(re.split(r"\n\s*\n", chunk), 1):
                plain = converter.latex_to_text(part).strip()
                if plain:
                    paragraphs.append((f"{file.relative_to(project_root)}:{offset}:{index}", plain))

        for match in pattern.finditer(text):
            add(text[start : match.start()], start)
            include = resolve(match[1], ".tex", file.parent)
            if include:
                visit(include)
            start = match.end()
        add(text[start:], start)
        active.remove(file)

    visit(path.resolve())
    return paragraphs, references, source_hashes


def parse_document(*, text: str | None = None, path: Path | None = None) -> dict:
    if (text is None) == (path is None):
        raise ValueError("Provide exactly one of text or input file.")
    warnings: list[str] = []
    references: list[dict] = []
    source_hashes = {}
    if path:
        path = path.resolve()
        source_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix.lower() == ".docx":
            paragraphs, references = _docx(path, warnings)
        elif path.suffix.lower() == ".tex":
            paragraphs, references, source_hashes = _tex(path, warnings)
        elif path.suffix.lower() == ".txt":
            text = path.read_text(encoding="utf-8")
            paragraphs = [
                (f"paragraph:{i}", p.strip())
                for i, p in enumerate(re.split(r"\n\s*\n", text), 1)
                if p.strip()
            ]
        else:
            raise ValueError("Supported document formats: .txt, .docx, .tex")
    else:
        source_hashes["inline"] = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        paragraphs = [
            (f"paragraph:{i}", p.strip())
            for i, p in enumerate(re.split(r"\n\s*\n", text or ""), 1)
            if p.strip()
        ]
    # TXT/DOCX reference sections may share a paragraph with their heading.
    body = []
    ref_lines = []
    in_references = False
    for location, paragraph in paragraphs:
        if location.startswith(("word/footnotes.xml:", "word/endnotes.xml:")):
            body.append((location, paragraph))
            continue
        kept = []
        for line in paragraph.splitlines():
            if REFERENCE_HEADING.match(line.strip()):
                in_references = True
                continue
            if in_references:
                ref_lines.append(line)
            else:
                kept.append(line)
        if kept:
            body.append((location, "\n".join(kept)))
    references.extend(_plain_references(ref_lines, warnings))
    unique_refs = {}
    for ref in references:
        if ref["key"] in unique_refs:
            warnings.append(f"Duplicate citation key: {ref['key']}; preserved first entry.")
        else:
            unique_refs[ref["key"]] = ref
    segments = []
    for location, paragraph in body:
        segment_id = stable_id("s_", location + "\n" + paragraph)
        statements = []
        for sentence in split_sentences(paragraph, minimum_length=3) or [paragraph]:
            if statements and re.fullmatch(r"(?:\[(?:cite:[^]]+|[\d,\s]+)\]\s*)+", sentence):
                statements[-1] += " " + sentence
            else:
                statements.append(sentence)
        for index, sentence in enumerate(statements):
            citation_keys = re.findall(r"\[cite:([^]]+)\]|\[(\d+(?:\s*,\s*\d+)*)\]", sentence)
            keys = [
                key.strip()
                for groups in citation_keys
                for group in groups
                if group
                for key in group.split(",")
            ]
            segments.append(
                {
                    "id": stable_id("c_", segment_id + str(index) + sentence),
                    "segment_id": segment_id,
                    "location": location,
                    "text": sentence,
                    "citation_keys": keys,
                }
            )
    return {
        "input": str(path) if path else "inline",
        "claims": segments,
        "existing_references": list(unique_refs.values()),
        "warnings": warnings,
        "source_hashes": source_hashes,
    }
