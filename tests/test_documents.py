import hashlib
import json
import zipfile
from xml.sax.saxutils import escape

from autoreference.documents import parse_document, read_bibtex


def test_txt_preserves_positions_and_raw_references(tmp_path):
    file = tmp_path / "paper.txt"
    file.write_text("移位窗口建立跨区域联系。[1]\n\n参考文献\n[1] Liu et al. Swin. 2021.\n")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    result = parse_document(path=file)
    assert result["claims"][0]["location"] == "paragraph:1"
    assert result["existing_references"][0]["key"] == "1"
    assert result["existing_references"][0]["candidate"] is None
    assert digest == hashlib.sha256(file.read_bytes()).hexdigest()


def test_docx_tables_fields_footnotes_and_references(tmp_path):
    file = tmp_path / "paper.docx"
    with zipfile.ZipFile(file, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>A supported claim.</w:t></w:r>
<w:r><w:instrText> ADDIN ZOTERO_ITEM CSL_CITATION </w:instrText></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Evidence in a table.</w:t></w:r></w:p></w:tc>
</w:tr></w:tbl>
        <w:p><w:r><w:t>References</w:t></w:r></w:p>
<w:p><w:r><w:t>[1] A. Author. Title. 2020.</w:t></w:r></w:p>
        </w:body></w:document>""",
        )
        archive.writestr(
            "word/footnotes.xml",
            """<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:footnote w:id="1"><w:p><w:r><w:t>A note.</w:t></w:r></w:p></w:footnote>
</w:footnotes>""",
        )
    result = parse_document(path=file)
    assert any("table" in c["text"] for c in result["claims"])
    assert result["existing_references"][0]["key"] == "1"
    assert any("ZOTERO" in w for w in result["warnings"])
    assert any("A note" in c["text"] for c in result["claims"])


def test_tex_includes_bibliography_keys_and_does_not_execute(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.tex").write_text(r"""\documentclass{article}
\addbibresource{refs.bib}
\begin{document}
Context \cite{original}.
\input{chapter}
\input{../outside}
\input{missing}
\write18{touch should-not-exist}
\end{document}""")
    (root / "chapter.tex").write_text(r"Second claim. \input{main}")
    (root / "refs.bib").write_text(
        "@article{original, title={A title}, author={张三 and Jane Doe}, year={2020}}"
    )
    (tmp_path / "outside.tex").write_text("Private outside text")
    result = parse_document(path=root / "main.tex")
    assert result["existing_references"][0]["key"] == "original"
    assert any("Second claim" in c["text"] for c in result["claims"])
    assert any("Circular" in w for w in result["warnings"])
    assert any("Blocked" in w for w in result["warnings"])
    assert any("Missing" in w for w in result["warnings"])
    assert not (root / "should-not-exist").exists()
    assert "Private outside" not in str(result)


def test_bibtex_duplicates_and_malformed_entries_are_reported():
    warnings = []
    refs = read_bibtex(
        "@article{x,title={One}}\n@article{x,title={Two}}\n@article{broken", warnings
    )
    assert len(refs) == 1
    assert any("Duplicate" in w for w in warnings)
    assert any("could not be parsed" in w for w in warnings)


def test_tex_inline_bibliography_is_not_body(tmp_path):
    file = tmp_path / "paper.tex"
    file.write_text(r"""\begin{document}
A body claim \cite{liu}.
\begin{thebibliography}{9}
\bibitem{liu} Liu. Swin Transformer. 2021.
\end{thebibliography}
\end{document}""")
    parsed = parse_document(path=file)
    assert parsed["existing_references"][0]["key"] == "liu"
    assert all("Transformer" not in c["text"] for c in parsed["claims"])


def test_docx_csl_citation_fields_are_structured(tmp_path):
    file = tmp_path / "paper.docx"
    data = {
        "citationItems": [
            {
                "id": 42,
                "itemData": {
                    "title": "Actual title",
                    "author": [{"given": "Jane", "family": "Doe"}],
                    "issued": {"date-parts": [[2021]]},
                    "DOI": "10.1234/example",
                },
            }
        ]
    }
    field = escape(" ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(data))
    document = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>A claim.</w:t></w:r>"
        f"<w:r><w:instrText>{field}</w:instrText></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(file, "w") as archive:
        archive.writestr("word/document.xml", document)
    parsed = parse_document(path=file)
    ref = parsed["existing_references"][0]
    assert ref["candidate"]["title"] == "Actual title"
    assert ref["candidate"]["year"] == 2021
    assert ref["key"] in parsed["claims"][0]["citation_keys"]


def test_wrapped_numbered_references_are_not_split_into_fake_entries():
    result = parse_document(
        text="A claim.\n\nReferences\n[1] Jane Doe.\n"
        "Actual title. 2021.\n[2] Someone. Another title. 2020."
    )
    refs = result["existing_references"]
    assert len(refs) == 2
    assert refs[0]["key"] == "1"
    assert "Actual title" in refs[0]["raw"]
