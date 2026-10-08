from autoreference.matching import deduplicate
from autoreference.models import ReferenceCandidate


def paper(source, **kwargs):
    return ReferenceCandidate(
        source=source, title="材料模型的定量分析", year=2020, authors=["张三"], **kwargs
    )


def test_missing_doi_title_match_and_conflicts():
    merged = deduplicate(
        [paper("openalex", doi="10.1/a", volume="1"), paper("anysearch", volume="2")]
    )
    assert len(merged) == 1
    assert merged[0].sources == ["openalex", "anysearch"]
    assert merged[0].match_method == "title-exact"
    assert merged[0].metadata_status == "unverified"
    assert merged[0].conflicts[0]["field"] == "volume"


def test_different_dois_are_never_merged():
    assert len(deduplicate([paper("a", doi="10.1/a"), paper("b", doi="10.1/b")])) == 2


def test_different_years_without_doi_are_not_merged():
    left = paper("a")
    right = left.model_copy(update={"year": 2021, "source": "b"})
    assert len(deduplicate([left, right])) == 2


def test_session_parameters_are_not_recorded():
    reference = paper(
        "campus",
        url="https://user:secret@example.com/paper?id=42&ticket=private",
        source_id="https://example.com/paper?api_key=secret&id=42",
    )
    assert reference.url == "https://example.com/paper?id=42"
    assert "secret" not in str(reference.model_dump())
    assert "private" not in str(reference.model_dump())
