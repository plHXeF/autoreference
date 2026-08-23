from autoreference.text import normalize_text, search_tokens, split_sentences


def test_normalize_text_preserves_word_boundaries() -> None:
    assert normalize_text("Swin\n Transformer  模型") == "Swin Transformer 模型"


def test_split_sentences_handles_chinese_and_decimal() -> None:
    text = "模型准确率达到92.5%。This is supported by prior work. 下一句也足够长。"
    assert split_sentences(text) == [
        "模型准确率达到92.5%。",
        "This is supported by prior work.",
        "下一句也足够长。",
    ]


def test_search_tokens_supports_chinese_and_latin() -> None:
    tokens = search_tokens("Swin Transformer 用于岩芯分析")
    assert "swin" in tokens
    assert "transformer" in tokens
    assert "岩芯" in tokens

