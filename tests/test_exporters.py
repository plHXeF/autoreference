import csv
import io

from autoreference.exporters import citation_key, export_bibtex, export_csv
from autoreference.models import CitationAssessment, ReferenceCandidate


def candidate() -> ReferenceCandidate:
    return ReferenceCandidate(
        source="crossref",
        title="Attention & geology: a review",
        authors=["Jane Doe", "张三"],
        year=2024,
        journal="Earth Science",
        doi="https://doi.org/10.1000/XYZ",
        url="https://doi.org/10.1000/xyz",
        assessment=CitationAssessment(relevance_score=88, can_cite=True, reason="Direct"),
    )


def test_bibtex_is_deterministic_and_escaped() -> None:
    item = candidate()
    output = export_bibtex([item])
    assert citation_key(item) in output
    assert "Attention \\& geology" in output
    assert "doi = {10.1000/xyz}" in output


def test_bibtex_escapes_all_latex_special_characters() -> None:
    item = ReferenceCandidate(
        source="test",
        title=r"CO_2 costs $5 & rises 50% #1 ~ ^ \ {draft}",
    )

    output = export_bibtex([item])

    assert (
        r"title = {CO\_2 costs \$5 \& rises 50\% \#1 "
        r"\textasciitilde{} \textasciicircum{} \textbackslash{} \{draft\}},"
    ) in output


def test_csv_is_real_csv() -> None:
    rows = list(csv.reader(io.StringIO(export_csv([candidate()]))))
    assert rows[0][0] == "citation_key"
    assert rows[1][1] == "Attention & geology: a review"
    assert rows[1][-1] == "88"


def test_verified_existing_bibtex_is_enriched_without_changing_key():
    import bibtexparser

    item = candidate()
    item.bibtex = "@misc{original,title={Attention & geology: a review},note={Keep this note}}"
    item.metadata_status = "verified"
    authoritative = item.model_copy(
        update={
            "volume": "3",
            "pages": "10-20",
            "publication_type": "journal-article",
            "bibtex": None,
        }
    )
    item.verification = {"authoritative_record": authoritative.model_dump()}
    database = bibtexparser.loads(export_bibtex([item]))
    assert database.entries[0]["ID"] == "original"
    assert database.entries[0]["volume"] == "3"
    assert database.entries[0]["pages"] == "10-20"
    assert database.entries[0]["note"] == "Keep this note"
    assert database.entries[0]["ENTRYTYPE"] == "article"
