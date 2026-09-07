import csv
import json

from merge_raw import merge_files, provenance_rows, write_provenance
from scraper import Article, read_jsonl, write_jsonl


def article(title: str, content: str, url: str) -> Article:
    return Article(title, "2026-08-30", "Notícias", content, url, "2026-08-31T00:00:00+00:00")


def test_merge_files_unites_parts_and_existing_history(tmp_path):
    raw = tmp_path / "raw" / "noticias.jsonl"
    processed = tmp_path / "processed" / "noticias.jsonl"
    history = article("Antiga", "conteúdo antigo com palavras suficientes", "/antiga")
    write_jsonl([history], raw)

    part_a = tmp_path / "a.jsonl"
    part_b = tmp_path / "b.jsonl"
    write_jsonl(
        [
            article("Compartilhada", "versão da parte a com texto", "/compartilhada"),
            article("Curta", "curta", "/curta"),
        ],
        part_a,
    )
    write_jsonl(
        [
            article("Compartilhada atualizada", "versão da parte b com texto", "/compartilhada"),
            article("ANTIGA!", "Conteúdo antigo, com palavras suficientes.", "/republicada"),
        ],
        part_b,
    )

    merged, clean, duplicates, short = merge_files([part_a, part_b], raw, processed, minimum_words=3)

    assert [a.url for a in merged] == ["/antiga", "/compartilhada", "/curta", "/republicada"]
    assert merged[1].title == "Compartilhada atualizada"
    assert [a.url for a in clean] == ["/antiga", "/compartilhada"]
    assert duplicates == 1
    assert short == 1
    assert read_jsonl(raw) == merged
    assert read_jsonl(processed) == clean
    with processed.with_suffix(".csv").open(encoding="utf-8") as stream:
        assert [row["url"] for row in csv.DictReader(stream)] == ["/antiga", "/compartilhada"]


def test_merge_files_works_without_previous_history(tmp_path):
    raw = tmp_path / "noticias.jsonl"
    processed = tmp_path / "processed.jsonl"
    part = tmp_path / "part.jsonl"
    write_jsonl([article("Nova", "texto novo suficiente", "/nova")], part)

    merged, clean, duplicates, short = merge_files([part], raw, processed, minimum_words=0)

    assert len(merged) == len(clean) == 1
    assert duplicates == short == 0
    assert json.loads(raw.read_text(encoding="utf-8"))["url"] == "/nova"


def test_provenance_crosses_listing_with_declared_category(tmp_path):
    transito = tmp_path / "transito.jsonl"
    write_jsonl(
        [
            Article("A", "2026-08-30", "Ocorrências", "texto", "/a", "agora"),
            Article("B", "2026-08-30", "Trânsito", "texto", "/b", "agora"),
            Article("C", "2026-08-30", "Ocorrências", "texto", "/c", "agora"),
            Article("D", "2026-08-30", "", "texto", "/d", "agora"),
        ],
        transito,
    )
    assert provenance_rows([transito]) == [
        {"listing": "transito", "declared_category": "Ocorrências", "count": 2},
        {"listing": "transito", "declared_category": "Trânsito", "count": 1},
        {"listing": "transito", "declared_category": "Sem categoria", "count": 1},
    ]
    destination = tmp_path / "reports" / "listing_vs_category.csv"
    write_provenance([transito], destination)
    with destination.open(encoding="utf-8") as stream:
        assert [row["declared_category"] for row in csv.DictReader(stream)] == ["Ocorrências", "Trânsito", "Sem categoria"]
