from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    """Keep word boundaries while removing layout noise from extracted paper text."""
    text = text.replace("\u3000", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r" {2,}", " ", text).strip()


def split_sentences(text: str, minimum_length: int = 6) -> list[str]:
    """Split Chinese/English prose without breaking decimal numbers."""
    normalized = normalize_text(text)
    if not normalized:
        return []

    sentences: list[str] = []
    start = 0
    for index, char in enumerate(normalized):
        boundary = char in "。！？!?"
        if char == ".":
            previous = normalized[index - 1] if index else ""
            following = normalized[index + 1] if index + 1 < len(normalized) else ""
            boundary = not (previous.isdigit() and following.isdigit()) and (
                not following or following.isspace()
            )
        if boundary:
            sentence = normalized[start : index + 1].strip()
            if len(sentence) >= minimum_length:
                sentences.append(sentence)
            start = index + 1

    tail = normalized[start:].strip()
    if len(tail) >= minimum_length:
        sentences.append(tail)
    return sentences


def search_tokens(text: str) -> set[str]:
    """Generate lightweight multilingual tokens for offline fallback ranking."""
    lowered = text.casefold()
    latin = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", lowered))
    chinese_chunks = re.findall(r"[\u3400-\u9fff]+", lowered)
    bigrams = {
        chunk[index : index + 2]
        for chunk in chinese_chunks
        for index in range(max(0, len(chunk) - 1))
    }
    return latin | bigrams
