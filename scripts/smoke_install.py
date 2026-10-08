#!/usr/bin/env python3
"""Exercise real installation and all three document adapters without network searches."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def command(arguments: list[str]) -> dict:
    result = subprocess.run(arguments, check=True, text=True, stdout=subprocess.PIPE)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    installer = Path(__file__).with_name("install_skill.py")
    with tempfile.TemporaryDirectory(prefix="autoreference install ") as folder:
        root = Path(folder)
        target = root / "skill with spaces"
        install = [
            sys.executable,
            str(installer),
            "--skill-dir",
            str(target),
            "--wheel",
            str(args.wheel.resolve()),
        ]
        if args.wheelhouse:
            install += ["--wheelhouse", str(args.wheelhouse.resolve())]
        command(install)
        launcher = [sys.executable, str(target / "scripts/run.py")]
        doctor = command([*launcher, "doctor"])["data"]
        assert doctor["extras"] == {"web": False, "llm": False, "campus": False}
        (root / "paper.txt").write_text("An original result.\n", encoding="utf-8")
        (root / "paper.tex").write_text(
            r"\begin{document}An original result.\end{document}", encoding="utf-8"
        )
        with zipfile.ZipFile(root / "paper.docx", "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>An original result.</w:t></w:r>"
                "</w:p></w:body></w:document>",
            )
        for suffix in ("txt", "docx", "tex"):
            task = root / f"task-{suffix}"
            prepared = command(
                [
                    *launcher,
                    "task",
                    "prepare",
                    "--input",
                    str(root / f"paper.{suffix}"),
                    "--output",
                    str(task),
                ]
            )
            claims = prepared["data"]["document"]["claims"]
            assert claims
            decisions = root / "decisions.json"
            decisions.write_text(
                json.dumps({"skipped_claims": {c["id"]: "Original result." for c in claims}})
            )
            exported = command(
                [*launcher, "task", "finalize", str(task), "--decisions", str(decisions)]
            )
            assert exported["data"]["reference_count"] == 0
            assert (task / "references.bib").is_file()
        # The manifest owns only installation components; user research survives uninstall.
        (target / "user-paper.txt").write_text("Keep this research.")
        command(
            [
                sys.executable,
                str(installer),
                "--skill-dir",
                str(target),
                "--update",
                "--wheel",
                str(args.wheel.resolve()),
                *(["--wheelhouse", str(args.wheelhouse.resolve())] if args.wheelhouse else []),
            ]
        )
        command([*launcher, "doctor"])
        command([sys.executable, str(installer), "--skill-dir", str(target), "--uninstall"])
        assert (target / "user-paper.txt").read_text() == "Keep this research."
    print(
        json.dumps(
            {
                "status": "success",
                "formats": ["txt", "docx", "tex"],
                "model_extra_required": False,
                "update": "passed",
                "uninstall_preserves_user_files": True,
            }
        )
    )


if __name__ == "__main__":
    main()
