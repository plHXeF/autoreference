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


def test_csv_is_real_csv() -> None:
    rows = list(csv.reader(io.StringIO(export_csv([candidate()]))))
    assert rows[0][0] == "citation_key"
    assert rows[1][1] == "Attention & geology: a review"
    assert rows[1][-1] == "88"

