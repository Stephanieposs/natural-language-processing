import json

import pytest

from preprocess import normalize_text, preprocess_file, preprocess_record, tokenize


def test_normalize_and_tokenize_preserve_portuguese_accents():
    text = normalize_text("  TRÂNSITO\n em Blumenau!  ")
    assert text == "trânsito em blumenau!"
    assert tokenize(text) == ["trânsito", "em", "blumenau"]


def test_preprocess_preserves_original_fields_and_builds_model_text():
    original = {"title": "Evento no Centro", "content": "A festa será em Blumenau.", "url": "/1"}
    result = preprocess_record(original)
    assert result["title"] == original["title"]
    assert result["content"] == original["content"]
    assert result["tokens"] == ["evento", "no", "centro", "a", "festa", "será", "em", "blumenau"]
    assert result["tokens_without_stopwords"] == ["evento", "centro", "festa", "blumenau"]
    assert result["text_for_model"] == "evento centro festa blumenau"


def test_stopword_list_covers_verb_forms_and_news_contractions():
    from preprocess import PORTUGUESE_STOPWORDS

    assert {"será", "está", "foram", "nesta", "deste", "não"} <= PORTUGUESE_STOPWORDS
    assert {"blumenau", "chuva", "acidente"}.isdisjoint(PORTUGUESE_STOPWORDS)
    assert len(PORTUGUESE_STOPWORDS) > 200


def test_preprocess_file_writes_jsonl_atomically(tmp_path):
    source = tmp_path / "source.jsonl"
    destination = tmp_path / "nested" / "output.jsonl"
    source.write_text(json.dumps({"title": "Saúde", "content": "Notícia local"}) + "\n", encoding="utf-8")
    assert preprocess_file(source, destination) == 1
    assert json.loads(destination.read_text(encoding="utf-8"))["tokens"] == ["saúde", "notícia", "local"]
    assert not destination.with_suffix(".jsonl.tmp").exists()


def test_preprocess_file_does_not_replace_output_on_invalid_input(tmp_path):
    source = tmp_path / "invalid.jsonl"
    destination = tmp_path / "output.jsonl"
    source.write_text("{inválido}\n", encoding="utf-8")
    destination.write_text("conteúdo anterior\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON inválido"):
        preprocess_file(source, destination)
    assert destination.read_text(encoding="utf-8") == "conteúdo anterior\n"


def test_preprocess_requires_an_existing_dataset(tmp_path):
    with pytest.raises(FileNotFoundError, match="Base processada não encontrada"):
        preprocess_file(tmp_path / "missing.jsonl", tmp_path / "output.jsonl")
